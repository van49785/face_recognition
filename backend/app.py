from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import face_recognition
import cv2
import numpy as np
import base64
import os
import boto3
from botocore.exceptions import ClientError
import json
import logging  
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///attendance.db')
db = SQLAlchemy(app)
CORS(app, resources={r"/*": {"origins": "*"}})  # Cấu hình CORS để hỗ trợ tất cả các origins
logging.basicConfig(filename='attendance.log', level=logging.INFO)

# Models
class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    image = db.Column(db.String(100), nullable=False)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))

# Load known faces
# known_faces = []
# known_names = []

def load_face_database():
    global known_faces, known_names
    known_faces = []
    known_names = []
    use_s3 = os.getenv('USE_S3', 'false').lower() == 'true'
    s3_client = boto3.client('s3') if use_s3 else None 
    bucket_name = os.getenv('S3_BUCKET', 'face-attendance-bucket')
    try:
        with open('data/employees.json') as f:
            employees = json.load(f)
            logging.info(f"Đang tải {len(employees)} nhân viên từ employees.json")
            for emp in employees:
                try:
                    if use_s3 and s3_client:
                        s3_client.download_file(bucket_name, f"known_faces/{emp['image']}", f"/tmp/{emp['image']}")
                        img_path = f"/tmp/{emp['image']}"
                        logging.info(f"Đang tải ảnh từ S3: {img_path}")
                    else:
                        img_path = f"data/know_faces/{emp['image']}"
                        logging.info(f"Đang tải ảnh: {img_path}")
                    img = face_recognition.load_image_file(img_path)
                    encodings = face_recognition.face_encodings(img)
                    if encodings:
                        known_faces.append(encodings[0])
                        known_names.append(emp['name'])
                        logging.info(f"Đã tải nhân viên: {emp['name']}")
                    else:
                        logging.warning(f"Không thể tạo face encoding cho {emp['name']} từ ảnh {img_path}")
                except Exception as e:
                    logging.error(f"Lỗi khi xử lý nhân viên {emp.get('name', 'unknown')}: {str(e)}")
        logging.info(f"Đã tải thành công {len(known_faces)} khuôn mặt vào cơ sở dữ liệu")
    except Exception as e:
        logging.error(f"Lỗi khi tải dữ liệu nhân viên: {str(e)}")

# Ban đầu tải dữ liệu khuôn mặt
load_face_database()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "OK", "known_faces_count": len(known_faces)})

@app.route('/debug-info', methods=['GET'])
def debug_info():
    """Endpoint để kiểm tra thông tin về cơ sở dữ liệu khuôn mặt hiện tại."""
    try:
        return jsonify({
            "known_faces_count": len(known_faces),
            "known_names": known_names,
            "status": "OK"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/reload-database', methods=['POST'])
def reload_database():
    """Endpoint để tải lại cơ sở dữ liệu khuôn mặt."""
    try:
        load_face_database()
        return jsonify({
            "status": "Database reloaded",
            "known_faces_count": len(known_faces),
            "known_names": known_names
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/recognize', methods=['POST'])
def recognize():
    try:
        data = request.json
        if not data or 'image' not in data:
            logging.error("Không có dữ liệu hình ảnh được gửi đến")
            return jsonify({"error": "Không có dữ liệu hình ảnh"}), 400
            
        # Kiểm tra định dạng base64
        image_data = data['image']
        if not image_data.startswith('data:image'):
            logging.error("Định dạng hình ảnh không hợp lệ")
            return jsonify({"error": "Định dạng hình ảnh không hợp lệ, phải là base64"}), 400
            
        img_data = base64.b64decode(image_data.split(',')[1])
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            logging.error("Không thể giải mã hình ảnh")
            return jsonify({"error": "Không thể giải mã hình ảnh"}), 400

        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        face_encodings = face_recognition.face_encodings(rgb_img)

        if not face_encodings:
            logging.warning("Không tìm thấy khuôn mặt")
            return jsonify({"error": "Không tìm thấy khuôn mặt"}), 400

        for face_encoding in face_encodings:
            matches = face_recognition.compare_faces(known_faces, face_encoding)
            name = "Unknown"
            for i, match in enumerate(matches):
                if match:
                    name = known_names[i]
                    break

            employee = Employee.query.filter_by(name=name).first()
            if employee:
                attendance = Attendance(employee_id=employee.id)
                db.session.add(attendance)
                db.session.commit()
                logging.info(f"Điểm danh {name} lúc {datetime.now(timezone.utc)}")
                return jsonify({"name": name, "timestamp": attendance.timestamp.isoformat()})

        return jsonify({"error": "Không thể nhận diện nhân viên"}), 404  # Chỉ chạy nếu không tìm thấy nhân viên nào

    except Exception as e:
        logging.error(f"Lỗi khi xử lý ảnh: {str(e)}")
        return jsonify({"error": f"Lỗi khi xử lý ảnh: {str(e)}"}), 500
    
@app.route('/upload-recognize', methods=['POST', 'OPTIONS'])
def upload_recognize():
    # Xử lý CORS preflight request
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        # Log thông tin request để debug
        logging.info("Nhận request upload-recognize")
        
        # Kiểm tra dữ liệu đầu vào
        data = request.json
        if not data or 'image' not in data:
            logging.error("Không có dữ liệu hình ảnh được gửi đến")
            return jsonify({"error": "Không có dữ liệu hình ảnh"}), 400
            
        # Kiểm tra định dạng base64
        image_data = data['image']
        if not image_data.startswith('data:image'):
            logging.error("Định dạng hình ảnh không hợp lệ")
            return jsonify({"error": "Định dạng hình ảnh không hợp lệ, phải là base64"}), 400
        
        # Giải mã base64
        try:
            img_data = base64.b64decode(image_data.split(',')[1])
            nparr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                logging.error("Không thể giải mã hình ảnh")
                return jsonify({"error": "Không thể giải mã hình ảnh"}), 400
                
            # Lưu ảnh để debug nếu cần
            cv2.imwrite('last_uploaded.jpg', img)
            logging.info("Đã lưu ảnh tải lên để debug")
        except Exception as e:
            logging.error(f"Lỗi khi giải mã ảnh: {str(e)}")
            return jsonify({"error": f"Lỗi khi giải mã ảnh: {str(e)}"}), 400

        # Chuyển đổi sang RGB và tìm khuôn mặt
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_img)
        
        logging.info(f"Số lượng khuôn mặt phát hiện: {len(face_locations)}")
        
        if not face_locations:
            logging.warning("Không tìm thấy khuôn mặt trong ảnh đã tải lên")
            return jsonify({"error": "Không tìm thấy khuôn mặt trong ảnh đã tải lên"}), 400
        
        face_encodings = face_recognition.face_encodings(rgb_img, face_locations)
        
        # Debug logging
        logging.info(f"Tìm thấy {len(face_encodings)} khuôn mặt trong ảnh đã tải lên")
        logging.info(f"Có {len(known_faces)} khuôn mặt trong cơ sở dữ liệu")
        
        if len(known_faces) == 0:
            logging.error("Không có khuôn mặt nào trong cơ sở dữ liệu")
            return jsonify({"error": "Không có khuôn mặt nào trong cơ sở dữ liệu"}), 500
            
        # Xử lý từng khuôn mặt tìm thấy
        for face_encoding in face_encodings:
            # Sử dụng tolerance cao hơn (dễ match hơn) cho ảnh đã biết
            matches = face_recognition.compare_faces(known_faces, face_encoding, tolerance=0.5)
            
            # Sử dụng phương pháp khoảng cách để cải thiện độ chính xác
            face_distances = face_recognition.face_distance(known_faces, face_encoding)
            
            # Nếu không có khuôn mặt nào trong cơ sở dữ liệu, face_distances sẽ trống
            if len(face_distances) == 0:
                continue
                
            best_match_index = np.argmin(face_distances)
            
            # Debug distances
            min_distance = face_distances[best_match_index]
            logging.info(f"Khoảng cách nhỏ nhất: {min_distance}, với {known_names[best_match_index]}")
            
            # Kiểm tra nếu có ít nhất một khuôn mặt khớp hoặc khoảng cách đủ nhỏ
            if True in matches or min_distance < 0.5:  # Nới lỏng ngưỡng
                name = known_names[best_match_index]
                logging.info(f"Đã khớp với: {name}, khoảng cách: {min_distance}")
                
                # Tạo entry điểm danh cho nhân viên
                employee = Employee.query.filter_by(name=name).first()
                if not employee:
                    # Nếu chưa có nhân viên trong DB, tạo mới
                    employee = Employee(name=name, image="uploaded_via_app.jpg")
                    db.session.add(employee)
                    db.session.commit()
                    
                attendance = Attendance(employee_id=employee.id)
                db.session.add(attendance)
                db.session.commit()
                logging.info(f"Điểm danh {name} lúc {datetime.now(timezone.utc)} qua ảnh đã tải lên")
                return jsonify({"name": name, "timestamp": attendance.timestamp.isoformat()})
        
        # Nếu không có kết quả khớp nào đủ tốt
        logging.warning("Không tìm thấy khuôn mặt khớp với độ chính xác yêu cầu")  
        return jsonify({"error": "Không thể nhận diện nhân viên trong ảnh đã tải lên"}), 404

    except Exception as e:
        logging.error(f"Lỗi khi xử lý ảnh đã tải lên: {str(e)}")
        return jsonify({"error": f"Lỗi khi xử lý ảnh đã tải lên: {str(e)}"}), 500

@app.route('/attendance', methods=['GET'])
def get_attendance():
    records = db.session.query(Attendance, Employee).join(Employee).all()
    return jsonify([{"name": emp.name, "timestamp": att.timestamp.isoformat()} for att, emp in records])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)