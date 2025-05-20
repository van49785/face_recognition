import React, { useRef, useState, useEffect } from "react";
import Webcam from "react-webcam";
import axios from "axios";
import { 
  Container, 
  Button, 
  Typography, 
  Box, 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableRow, 
  Paper,
  Tabs,
  Tab,
  Input,
  CircularProgress,
  IconButton,
  Snackbar,
  Alert
} from "@mui/material";
import RefreshIcon from '@mui/icons-material/Refresh';
import "./App.css";

function App() {
  const webcamRef = useRef(null);
  const fileInputRef = useRef(null);
  const [result, setResult] = useState(null);
  const [attendance, setAttendance] = useState([]);
  const [capturing, setCapturing] = useState(false);
  const [tabValue, setTabValue] = useState(0);
  const [uploadedImage, setUploadedImage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [debugInfo, setDebugInfo] = useState(null);
  const [snackbar, setSnackbar] = useState({
    open: false,
    message: "",
    severity: "info"
  });

  useEffect(() => {
    fetchAttendance();
    fetchDebugInfo();
  }, []);

  const fetchDebugInfo = async () => {
    try {
      const response = await axios.get("http://localhost:5000/debug-info");
      setDebugInfo(response.data);
    } catch (error) {
      console.error("Lỗi lấy thông tin debug", error);
    }
  };

  const reloadDatabase = async () => {
    try {
      setLoading(true);
      const response = await axios.post("http://localhost:5000/reload-database");
      setDebugInfo(response.data);
      setSnackbar({
        open: true,
        message: `Đã tải lại cơ sở dữ liệu. Đã tải ${response.data.known_faces_count} khuôn mặt.`,
        severity: "success"
      });
    } catch (error) {
      setSnackbar({
        open: true,
        message: `Lỗi khi tải lại cơ sở dữ liệu: ${error.response?.data?.error || error.message}`,
        severity: "error"
      });
    } finally {
      setLoading(false);
    }
  };

  const capture = async () => {
    if (!webcamRef.current) return;
    const imageSrc = webcamRef.current.getScreenshot();

    if (!imageSrc) {
      setResult({ error: "Không thể chụp ảnh, vui lòng kiểm tra webcam!" });
      return;
    }

    try {
      setLoading(true);
      const response = await axios.post("http://localhost:5000/recognize", { image: imageSrc });
      setResult(response.data);
      fetchAttendance();
    } catch (error) {
      setResult({ error: error.response?.data?.error || "Đã xảy ra lỗi khi nhận diện!" });
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      setUploadedImage(e.target.result);
    };
    reader.readAsDataURL(file);
  };

  const handleUploadRecognize = async () => {
    if (!uploadedImage) {
      setResult({ error: "Vui lòng tải lên ảnh trước!" });
      return;
    }

    try {
      setLoading(true);
      const response = await axios.post("http://localhost:5000/upload-recognize", { image: uploadedImage });
      setResult(response.data);
      fetchAttendance();
    } catch (error) {
      setResult({ error: error.response?.data?.error || "Đã xảy ra lỗi khi nhận diện!" });
    } finally {
      setLoading(false);
    }
  };

  const fetchAttendance = async () => {
    try {
      const response = await axios.get("http://localhost:5000/attendance");
      setAttendance(response.data);
    } catch (error) {
      console.error("Lỗi tải danh sách điểm danh", error);
    }
  };

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
    if (newValue === 0) {
      setUploadedImage(null);
    } else {
      setCapturing(false);
    }
  };

  const triggerFileInput = () => {
    fileInputRef.current.click();
  };

  const handleCloseSnackbar = () => {
    setSnackbar({ ...snackbar, open: false });
  };

  return (
    <Container maxWidth="md" style={{ textAlign: "center", padding: "20px" }}>
      <Typography variant="h4" gutterBottom>
        Hệ thống điểm danh bằng nhận diện khuôn mặt
      </Typography>
      
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="subtitle1">
          {debugInfo && `Đã tải ${debugInfo.known_faces_count} khuôn mặt`}
        </Typography>
        <IconButton onClick={reloadDatabase} disabled={loading}>
          <RefreshIcon />
        </IconButton>
      </Box>
      
      <Paper elevation={3} style={{ marginBottom: "20px" }}>
        <Tabs value={tabValue} onChange={handleTabChange} centered>
          <Tab label="Dùng Webcam" />
          <Tab label="Tải ảnh lên" />
        </Tabs>
      </Paper>

      {tabValue === 0 ? (
        // Webcam Tab
        <Box>
          <Box my={4}>
            <Button variant="contained" color="primary" onClick={() => setCapturing(!capturing)}>
              {capturing ? "Tắt Webcam" : "Bật Webcam"}
            </Button>
          </Box>
          {capturing && (
            <Box my={2}>
              <Webcam audio={false} ref={webcamRef} screenshotFormat="image/jpeg" style={{ maxWidth: "500px" }} />
              <Box my={2}>
                <Button 
                  variant="contained" 
                  color="secondary" 
                  onClick={capture}
                  disabled={loading}
                >
                  {loading ? <CircularProgress size={24} /> : "Điểm danh"}
                </Button>
              </Box>
            </Box>
          )}
        </Box>
      ) : (
        // Upload Tab
        <Box my={4}>
          <input
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            ref={fileInputRef}
            onChange={handleFileUpload}
          />
          <Button variant="contained" color="primary" onClick={triggerFileInput}>
            Chọn Ảnh
          </Button>
          
          {uploadedImage && (
            <Box my={2}>
              <img src={uploadedImage} alt="Uploaded" style={{ maxWidth: "500px", maxHeight: "400px" }} />
              <Box my={2}>
                <Button 
                  variant="contained" 
                  color="secondary" 
                  onClick={handleUploadRecognize}
                  disabled={loading}
                >
                  {loading ? <CircularProgress size={24} /> : "Điểm danh bằng ảnh"}
                </Button>
              </Box>
            </Box>
          )}
        </Box>
      )}

      {result && (
        <Box my={2}>
          {result.error ? (
            <Typography color="error">{result.error}</Typography>
          ) : (
            <Typography>
              Điểm danh thành công: {result.name} vào lúc{" "}
              {result.timestamp ? new Date(result.timestamp).toLocaleString() : "Không xác định"}
            </Typography>
          )}
        </Box>
      )}

      {attendance.length > 0 && (
        <Paper elevation={3} style={{ marginTop: "20px", padding: "10px" }}>
          <Typography variant="h6">Lịch sử điểm danh</Typography>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell><b>Tên</b></TableCell>
                <TableCell><b>Thời gian</b></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {attendance.map((entry, index) => (
                <TableRow key={index}>
                  <TableCell>{entry.name}</TableCell>
                  <TableCell>{new Date(entry.timestamp).toLocaleString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      <Snackbar open={snackbar.open} autoHideDuration={6000} onClose={handleCloseSnackbar}>
        <Alert onClose={handleCloseSnackbar} severity={snackbar.severity}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Container>
  );
}

export default App;