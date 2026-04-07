import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useWorkflow } from '../context/WorkflowContext';
import { ChartBar, Upload, SignOut, User, ArrowsClockwise, CheckCircle, Circle } from '@phosphor-icons/react';
import { motion } from 'framer-motion';

export function Layout({ children }) {
    const { user, logout } = useAuth();
    const { workflowState, resetWorkflow } = useWorkflow();
    const navigate = useNavigate();
    const location = useLocation();

    const handleLogout = async () => {
        await logout();
        navigate('/login');
    };

    const handleReset = async () => {
        if (window.confirm('Start a new analysis? This will clear all uploaded data.')) {
            await resetWorkflow();
            navigate('/upload/naukri');
        }
    };

    // Determine which nav items are accessible
    const getNavClass = (path, isActive) => {
        let accessible = false;
        if (path === '/upload/naukri') accessible = true;
        if (path === '/upload/pipeline') accessible = workflowState.naukri_uploaded;
        if (path === '/dashboard') accessible = workflowState.processing_complete;

        if (!accessible) {
            return 'nav-link flex items-center gap-2 text-sm opacity-50 cursor-not-allowed';
        }
        return `nav-link flex items-center gap-2 text-sm ${isActive ? 'active' : ''}`;
    };

    const getStepIcon = (step) => {
        if (step === 'naukri') {
            return workflowState.naukri_uploaded ? 
                <CheckCircle size={16} weight="fill" className="text-green-600" /> : 
                <Circle size={16} weight="bold" />;
        }
        if (step === 'pipeline') {
            return workflowState.pipeline_uploaded ? 
                <CheckCircle size={16} weight="fill" className="text-green-600" /> : 
                <Circle size={16} weight="bold" />;
        }
        if (step === 'dashboard') {
            return workflowState.processing_complete ? 
                <CheckCircle size={16} weight="fill" className="text-green-600" /> : 
                <Circle size={16} weight="bold" />;
        }
        return <Circle size={16} weight="bold" />;
    };

    return (
        <div className="min-h-screen bg-[#F9FAFB]">
            {/* Header */}
            <header className="bg-white border-b border-gray-200">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between h-16">
                        {/* Logo */}
                        <div className="flex items-center gap-8">
                            <NavLink to="/upload/naukri" className="flex items-center gap-2">
                                <div className="w-8 h-8 bg-[#002FA7] flex items-center justify-center">
                                    <ChartBar size={20} weight="bold" className="text-white" />
                                </div>
                                <span className="font-bold text-lg tracking-tight">RECRUIT<span className="text-[#002FA7]">IQ</span></span>
                            </NavLink>

                            {/* Navigation with workflow indicators */}
                            <nav className="hidden md:flex items-center gap-6">
                                <NavLink
                                    to="/upload/naukri"
                                    className={({ isActive }) => getNavClass('/upload/naukri', isActive)}
                                >
                                    {getStepIcon('naukri')}
                                    <Upload size={18} weight="bold" />
                                    Step 1: Naukri
                                </NavLink>
                                <NavLink
                                    to="/upload/pipeline"
                                    className={({ isActive }) => getNavClass('/upload/pipeline', isActive)}
                                    onClick={(e) => {
                                        if (!workflowState.naukri_uploaded) {
                                            e.preventDefault();
                                        }
                                    }}
                                >
                                    {getStepIcon('pipeline')}
                                    <Upload size={18} weight="bold" />
                                    Step 2: Pipeline
                                </NavLink>
                                <NavLink
                                    to="/dashboard"
                                    className={({ isActive }) => getNavClass('/dashboard', isActive)}
                                    onClick={(e) => {
                                        if (!workflowState.processing_complete) {
                                            e.preventDefault();
                                        }
                                    }}
                                >
                                    {getStepIcon('dashboard')}
                                    <ChartBar size={18} weight="bold" />
                                    Dashboard
                                </NavLink>
                            </nav>
                        </div>

                        {/* User menu */}
                        <div className="flex items-center gap-4">
                            {workflowState.processing_complete && (
                                <button
                                    onClick={handleReset}
                                    className="flex items-center gap-2 text-sm text-gray-600 hover:text-[#002FA7] transition-colors"
                                    title="Start New Analysis"
                                >
                                    <ArrowsClockwise size={18} weight="bold" />
                                    <span className="hidden sm:inline">New Analysis</span>
                                </button>
                            )}
                            <div className="flex items-center gap-2 text-sm text-gray-600">
                                <User size={18} weight="bold" />
                                <span className="hidden sm:inline">{user?.name || user?.email}</span>
                            </div>
                            <button
                                onClick={handleLogout}
                                className="flex items-center gap-2 text-sm text-gray-600 hover:text-[#E63946] transition-colors"
                                data-testid="logout-button"
                            >
                                <SignOut size={18} weight="bold" />
                                <span className="hidden sm:inline">Logout</span>
                            </button>
                        </div>
                    </div>
                </div>

                {/* Mobile Navigation */}
                <nav className="md:hidden border-t border-gray-200 px-4 py-2 flex gap-4 overflow-x-auto">
                    <NavLink
                        to="/upload/naukri"
                        className={({ isActive }) => `${getNavClass('/upload/naukri', isActive)} whitespace-nowrap`}
                    >
                        {getStepIcon('naukri')}
                        Naukri
                    </NavLink>
                    <NavLink
                        to="/upload/pipeline"
                        className={({ isActive }) => `${getNavClass('/upload/pipeline', isActive)} whitespace-nowrap`}
                        onClick={(e) => {
                            if (!workflowState.naukri_uploaded) e.preventDefault();
                        }}
                    >
                        {getStepIcon('pipeline')}
                        Pipeline
                    </NavLink>
                    <NavLink
                        to="/dashboard"
                        className={({ isActive }) => `${getNavClass('/dashboard', isActive)} whitespace-nowrap`}
                        onClick={(e) => {
                            if (!workflowState.processing_complete) e.preventDefault();
                        }}
                    >
                        {getStepIcon('dashboard')}
                        Dashboard
                    </NavLink>
                </nav>
            </header>

            {/* Main content */}
            <motion.main
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8"
            >
                {children}
            </motion.main>
        </div>
    );
}
