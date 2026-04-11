import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Summary from "./pages/Summary";
import Applicants from "./pages/Roles";
import AttendedApplicants from "./pages/AttendedRoles";
import { Toaster } from "./components/ui/sonner";

function App() {
    return (
        <div className="App">
            <AuthProvider>
                <BrowserRouter>
                    <Routes>
                        <Route path="/login" element={<Login />} />
                        <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
                        <Route path="/summary" element={<ProtectedRoute><Summary /></ProtectedRoute>} />
                        <Route path="/roles" element={<ProtectedRoute><Applicants /></ProtectedRoute>} />
                        <Route path="/attended-roles" element={<ProtectedRoute><AttendedApplicants /></ProtectedRoute>} />
                        <Route path="/" element={<Navigate to="/dashboard" replace />} />
                        <Route path="*" element={<Navigate to="/dashboard" replace />} />
                    </Routes>
                </BrowserRouter>
                <Toaster />
            </AuthProvider>
        </div>
    );
}

export default App;
