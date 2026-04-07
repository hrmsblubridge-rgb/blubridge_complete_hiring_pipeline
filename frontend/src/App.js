import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { WorkflowProvider } from "./context/WorkflowContext";
import { WorkflowRoute } from "./components/ProtectedRoute";
import Login from "./pages/Login";
import Register from "./pages/Register";
import UploadNaukri from "./pages/UploadNaukri";
import UploadPipeline from "./pages/UploadPipeline";
import Dashboard from "./pages/Dashboard";
import { Toaster } from "./components/ui/sonner";

function App() {
    return (
        <div className="App">
            <AuthProvider>
                <WorkflowProvider>
                    <BrowserRouter>
                        <Routes>
                            {/* Public routes */}
                            <Route path="/login" element={<Login />} />
                            <Route path="/register" element={<Register />} />
                            
                            {/* Workflow routes - Sequential access enforced */}
                            <Route
                                path="/upload/naukri"
                                element={
                                    <WorkflowRoute step="naukri">
                                        <UploadNaukri />
                                    </WorkflowRoute>
                                }
                            />
                            <Route
                                path="/upload/pipeline"
                                element={
                                    <WorkflowRoute step="pipeline">
                                        <UploadPipeline />
                                    </WorkflowRoute>
                                }
                            />
                            <Route
                                path="/dashboard"
                                element={
                                    <WorkflowRoute step="dashboard">
                                        <Dashboard />
                                    </WorkflowRoute>
                                }
                            />
                            
                            {/* Default redirect to upload naukri (entry point) */}
                            <Route path="/" element={<Navigate to="/upload/naukri" replace />} />
                            <Route path="*" element={<Navigate to="/upload/naukri" replace />} />
                        </Routes>
                    </BrowserRouter>
                    <Toaster />
                </WorkflowProvider>
            </AuthProvider>
        </div>
    );
}

export default App;
