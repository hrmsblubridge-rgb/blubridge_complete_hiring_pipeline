import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import Login from "./pages/Login";
import Home from "./pages/Home";
import Dashboard from "./pages/Dashboard";
import Summary from "./pages/Summary";
import Applicants from "./pages/Roles";
import AttendedApplicants from "./pages/AttendedRoles";
import JobsKeywords from "./pages/JobsKeywords";
import ManageJobRoles from "./pages/ManageJobRoles";
import HiringForms from "./pages/HiringForms";
import InterviewReports from "./pages/InterviewReports";
import UpdateScores from "./pages/UpdateScores";
import JobOpenings from "./pages/JobOpenings";
import { Toaster } from "./components/ui/sonner";

function App() {
    return (
        <div className="App">
            <AuthProvider>
                <BrowserRouter>
                    <Routes>
                        <Route path="/login" element={<Login />} />
                        <Route path="/home" element={<ProtectedRoute><Home /></ProtectedRoute>} />
                        <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
                        <Route path="/summary" element={<ProtectedRoute><Summary /></ProtectedRoute>} />
                        <Route path="/roles" element={<ProtectedRoute><Applicants /></ProtectedRoute>} />
                        <Route path="/attended-roles" element={<ProtectedRoute><AttendedApplicants /></ProtectedRoute>} />
                        <Route path="/jobs-keywords" element={<ProtectedRoute><JobsKeywords /></ProtectedRoute>} />
                        <Route path="/manage-job-roles" element={<ProtectedRoute><ManageJobRoles /></ProtectedRoute>} />
                        <Route path="/hiring-forms" element={<ProtectedRoute><HiringForms /></ProtectedRoute>} />
                        <Route path="/interview-reports" element={<ProtectedRoute><InterviewReports /></ProtectedRoute>} />
                        <Route path="/update-scores" element={<ProtectedRoute><UpdateScores /></ProtectedRoute>} />
                        <Route path="/job-openings" element={<ProtectedRoute><JobOpenings /></ProtectedRoute>} />
                        <Route path="/" element={<Navigate to="/home" replace />} />
                        <Route path="*" element={<Navigate to="/home" replace />} />
                    </Routes>
                </BrowserRouter>
                <Toaster />
            </AuthProvider>
        </div>
    );
}

export default App;
