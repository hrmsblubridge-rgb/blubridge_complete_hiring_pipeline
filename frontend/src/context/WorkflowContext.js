import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from './AuthContext';

const WorkflowContext = createContext(null);

const API = process.env.REACT_APP_BACKEND_URL;

export function WorkflowProvider({ children }) {
    const { user } = useAuth();
    const [workflowState, setWorkflowState] = useState({
        naukri_uploaded: false,
        pipeline_uploaded: false,
        processing_complete: false,
        current_step: 'naukri'
    });
    const [loading, setLoading] = useState(true);

    const fetchWorkflowState = useCallback(async () => {
        if (!user) {
            setWorkflowState({
                naukri_uploaded: false,
                pipeline_uploaded: false,
                processing_complete: false,
                current_step: 'naukri'
            });
            setLoading(false);
            return;
        }

        try {
            const response = await axios.get(`${API}/api/workflow/state`, {
                withCredentials: true
            });
            setWorkflowState(response.data);
        } catch (error) {
            console.error('Failed to fetch workflow state:', error);
        } finally {
            setLoading(false);
        }
    }, [user]);

    useEffect(() => {
        fetchWorkflowState();
    }, [fetchWorkflowState]);

    const resetWorkflow = async () => {
        try {
            await axios.post(`${API}/api/workflow/reset`, {}, {
                withCredentials: true
            });
            setWorkflowState({
                naukri_uploaded: false,
                pipeline_uploaded: false,
                processing_complete: false,
                current_step: 'naukri'
            });
            return { success: true };
        } catch (error) {
            console.error('Failed to reset workflow:', error);
            return { success: false, error: error.message };
        }
    };

    const processCombinedData = async () => {
        try {
            const response = await axios.post(`${API}/api/process-combined`, {}, {
                withCredentials: true
            });
            
            if (response.data.success) {
                setWorkflowState(prev => ({
                    ...prev,
                    processing_complete: true,
                    current_step: 'dashboard'
                }));
            }
            
            return response.data;
        } catch (error) {
            console.error('Failed to process data:', error);
            return { success: false, error: error.response?.data?.detail || error.message };
        }
    };

    const updateLocalState = (updates) => {
        setWorkflowState(prev => ({ ...prev, ...updates }));
    };

    const getNextRoute = () => {
        if (!workflowState.naukri_uploaded) return '/upload/naukri';
        if (!workflowState.pipeline_uploaded) return '/upload/pipeline';
        if (!workflowState.processing_complete) return '/upload/pipeline';
        return '/dashboard';
    };

    const canAccessRoute = (route) => {
        switch (route) {
            case '/upload/naukri':
                return true; // Always accessible
            case '/upload/pipeline':
                return workflowState.naukri_uploaded;
            case '/dashboard':
                return workflowState.processing_complete;
            default:
                return true;
        }
    };

    return (
        <WorkflowContext.Provider value={{
            workflowState,
            loading,
            fetchWorkflowState,
            resetWorkflow,
            processCombinedData,
            updateLocalState,
            getNextRoute,
            canAccessRoute
        }}>
            {children}
        </WorkflowContext.Provider>
    );
}

export function useWorkflow() {
    const context = useContext(WorkflowContext);
    if (!context) {
        throw new Error('useWorkflow must be used within a WorkflowProvider');
    }
    return context;
}
