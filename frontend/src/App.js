import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import UploadNaukri from "./pages/UploadNaukri";
import UploadPipeline from "./pages/UploadPipeline";
import { Toaster } from "./components/ui/sonner";

function App() {
    return (
        <div className="App">
            <AuthProvider>
                <BrowserRouter>
                    <Routes>
                        {/* Public routes */}
                        <Route path="/login" element={<Login />} />
                        <Route path="/register" element={<Register />} />
                        
                        {/* Protected routes */}
                        <Route
                            path="/dashboard"
                            element={
                                <ProtectedRoute>
                                    <Dashboard />
                                </ProtectedRoute>
                            }
                        />
                        <Route
                            path="/upload/naukri"
                            element={
                                <ProtectedRoute>
                                    <UploadNaukri />
                                </ProtectedRoute>
                            }
                        />
                        <Route
                            path="/upload/pipeline"
                            element={
                                <ProtectedRoute>
                                    <UploadPipeline />
                                </ProtectedRoute>
                            }
                        />
                        
                        {/* Default redirect */}
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
