import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useWorkflow } from '../context/WorkflowContext';

export function ProtectedRoute({ children, requiredStep }) {
    const { user, loading: authLoading } = useAuth();
    const { workflowState, loading: workflowLoading, canAccessRoute, getNextRoute } = useWorkflow();
    const location = useLocation();

    // Show loading while checking auth and workflow
    if (authLoading || workflowLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-white">
                <div className="flex flex-col items-center gap-4">
                    <div className="spinner"></div>
                    <p className="label-small">Loading...</p>
                </div>
            </div>
        );
    }

    // Not authenticated - redirect to login
    if (!user) {
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    // Check workflow access
    if (requiredStep) {
        const currentPath = location.pathname;
        
        if (!canAccessRoute(currentPath)) {
            const nextRoute = getNextRoute();
            return <Navigate to={nextRoute} replace />;
        }
    }

    return children;
}

// Workflow-aware route that enforces sequential access
export function WorkflowRoute({ children, step }) {
    const { user, loading: authLoading } = useAuth();
    const { workflowState, loading: workflowLoading, getNextRoute } = useWorkflow();
    const location = useLocation();

    if (authLoading || workflowLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-white">
                <div className="flex flex-col items-center gap-4">
                    <div className="spinner"></div>
                    <p className="label-small">Loading...</p>
                </div>
            </div>
        );
    }

    if (!user) {
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    // Enforce workflow sequence
    if (step === 'pipeline' && !workflowState.naukri_uploaded) {
        return <Navigate to="/upload/naukri" replace />;
    }

    if (step === 'dashboard' && !workflowState.processing_complete) {
        return <Navigate to={getNextRoute()} replace />;
    }

    return children;
}
