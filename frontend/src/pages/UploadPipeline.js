import { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { useWorkflow } from '../context/WorkflowContext';
import { motion } from 'framer-motion';
import { CloudArrowUp, FileXls, CheckCircle, XCircle, Warning, Info, ArrowRight, ArrowLeft, NumberCircleOne, NumberCircleTwo, NumberCircleThree, Spinner } from '@phosphor-icons/react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

export default function UploadPipeline() {
    const navigate = useNavigate();
    const { workflowState, updateLocalState, processCombinedData } = useWorkflow();
    const [file, setFile] = useState(null);
    const [dragging, setDragging] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [processing, setProcessing] = useState(false);
    const [progress, setProgress] = useState(0);
    const [result, setResult] = useState(null);
    const [processResult, setProcessResult] = useState(null);
    const [error, setError] = useState('');

    // Auto-process when both uploads are complete
    const handleAutoProcess = useCallback(async () => {
        if (result && result.success && !processResult) {
            setProcessing(true);
            try {
                const processResponse = await processCombinedData();
                setProcessResult(processResponse);
                if (processResponse.success) {
                    // Wait a moment then redirect
                    setTimeout(() => {
                        navigate('/dashboard');
                    }, 2000);
                }
            } catch (err) {
                setError('Processing failed. Please try again.');
            } finally {
                setProcessing(false);
            }
        }
    }, [result, processResult, processCombinedData, navigate]);

    useEffect(() => {
        handleAutoProcess();
    }, [handleAutoProcess]);

    const handleDragOver = useCallback((e) => {
        e.preventDefault();
        setDragging(true);
    }, []);

    const handleDragLeave = useCallback((e) => {
        e.preventDefault();
        setDragging(false);
    }, []);

    const handleDrop = useCallback((e) => {
        e.preventDefault();
        setDragging(false);
        const droppedFile = e.dataTransfer.files[0];
        if (droppedFile && (droppedFile.name.endsWith('.csv') || droppedFile.name.endsWith('.xlsx'))) {
            setFile(droppedFile);
            setResult(null);
            setProcessResult(null);
            setError('');
        } else {
            setError('Please upload a .csv or .xlsx file');
        }
    }, []);

    const handleFileSelect = (e) => {
        const selectedFile = e.target.files[0];
        if (selectedFile) {
            setFile(selectedFile);
            setResult(null);
            setProcessResult(null);
            setError('');
        }
    };

    const handleUpload = async () => {
        if (!file) return;

        setUploading(true);
        setProgress(0);
        setError('');
        setResult(null);
        setProcessResult(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await axios.post(`${API}/api/upload/pipeline`, formData, {
                withCredentials: true,
                headers: {
                    'Content-Type': 'multipart/form-data'
                },
                onUploadProgress: (progressEvent) => {
                    const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
                    setProgress(percentCompleted);
                }
            });

            setResult(response.data);
            updateLocalState({
                pipeline_uploaded: true,
                current_step: 'processing'
            });
            setFile(null);
            
            // Auto-process will be triggered by useEffect
        } catch (err) {
            setError(err.response?.data?.detail || 'Upload failed. Please try again.');
        } finally {
            setUploading(false);
        }
    };

    const handleGoBack = () => {
        navigate('/upload/naukri');
    };

    const handleGoToDashboard = () => {
        navigate('/dashboard');
    };

    return (
        <Layout>
            <div className="max-w-4xl mx-auto">
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                >
                    {/* Progress Steps */}
                    <div className="mb-8">
                        <div className="flex items-center justify-center gap-4">
                            <div className="flex items-center gap-2">
                                <NumberCircleOne size={32} weight="fill" className="text-green-600" />
                                <span className="font-bold text-green-600">Upload Naukri</span>
                                <CheckCircle size={20} weight="fill" className="text-green-600" />
                            </div>
                            <div className="w-16 h-0.5 bg-[#002FA7]"></div>
                            <div className="flex items-center gap-2">
                                <NumberCircleTwo size={32} weight="fill" className="text-[#002FA7]" />
                                <span className="font-bold text-[#002FA7]">Upload Pipeline</span>
                            </div>
                            <div className="w-16 h-0.5 bg-gray-300"></div>
                            <div className="flex items-center gap-2">
                                <NumberCircleThree size={32} weight={processResult?.success ? "fill" : "regular"} className={processResult?.success ? "text-green-600" : "text-gray-400"} />
                                <span className={processResult?.success ? "font-bold text-green-600" : "text-gray-400"}>Dashboard</span>
                            </div>
                        </div>
                    </div>

                    <h1 className="heading-1 mb-2">Step 2: Upload HRMS Pipeline Data</h1>
                    <p className="text-gray-500 mb-8">
                        Now upload your HR pipeline data with candidate statuses. After this, analytics will be generated automatically.
                    </p>

                    {/* Dynamic Schema Info */}
                    <div className="card mb-8 bg-blue-50 border-blue-200">
                        <div className="flex items-start gap-3">
                            <Info size={20} weight="fill" className="text-blue-600 flex-shrink-0 mt-0.5" />
                            <div>
                                <p className="font-semibold text-blue-900 mb-2">Dynamic Schema Detection</p>
                                <p className="text-sm text-blue-800 mb-3">
                                    The system will automatically detect your columns including:
                                </p>
                                <ul className="text-sm text-blue-700 space-y-1">
                                    <li>• <strong>Email</strong> or <strong>Phone</strong> column (for matching with Naukri data)</li>
                                    <li>• <strong>Status</strong> column (e.g., shortlisted, rejected, scheduled)</li>
                                    <li>• All other columns will be stored dynamically</li>
                                </ul>
                            </div>
                        </div>
                    </div>

                    {/* Processing indicator */}
                    {processing && (
                        <div className="card mb-8 bg-[#002FA7]/5 border-[#002FA7]">
                            <div className="flex items-center gap-4">
                                <div className="spinner"></div>
                                <div>
                                    <p className="font-semibold text-[#002FA7]">Processing both datasets...</p>
                                    <p className="text-sm text-gray-600">Matching candidates and generating analytics</p>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Process Result */}
                    {processResult && processResult.success && (
                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="card mb-8 bg-green-50 border-green-200"
                        >
                            <div className="flex items-start gap-3">
                                <CheckCircle size={24} weight="fill" className="text-green-600 flex-shrink-0 mt-0.5" />
                                <div className="flex-1">
                                    <p className="font-semibold text-green-900 mb-2">Processing Complete!</p>
                                    <div className="grid grid-cols-3 gap-4 mb-4">
                                        <div className="text-center p-3 bg-white border border-green-200">
                                            <p className="text-2xl font-bold text-gray-900">{processResult.total_processed}</p>
                                            <p className="text-xs uppercase tracking-wider text-gray-600">Total Processed</p>
                                        </div>
                                        <div className="text-center p-3 bg-white border border-green-200">
                                            <p className="text-2xl font-bold text-green-600">{processResult.registered}</p>
                                            <p className="text-xs uppercase tracking-wider text-gray-600">Registered</p>
                                        </div>
                                        <div className="text-center p-3 bg-white border border-green-200">
                                            <p className="text-2xl font-bold text-red-500">{processResult.not_registered}</p>
                                            <p className="text-xs uppercase tracking-wider text-gray-600">Not Registered</p>
                                        </div>
                                    </div>
                                    <p className="text-sm text-green-700 mb-4">Redirecting to dashboard...</p>
                                    <button
                                        onClick={handleGoToDashboard}
                                        className="btn-primary flex items-center gap-2"
                                        data-testid="go-to-dashboard-btn"
                                    >
                                        Go to Dashboard Now
                                        <ArrowRight size={18} weight="bold" />
                                    </button>
                                </div>
                            </div>
                        </motion.div>
                    )}

                    {/* Upload Zone - hide when processing complete */}
                    {!processResult?.success && (
                        <>
                            <div
                                className={`upload-zone ${dragging ? 'dragging' : ''}`}
                                onDragOver={handleDragOver}
                                onDragLeave={handleDragLeave}
                                onDrop={handleDrop}
                                onClick={() => document.getElementById('file-input').click()}
                                data-testid="upload-pipeline-input"
                            >
                                <input
                                    id="file-input"
                                    type="file"
                                    accept=".csv,.xlsx"
                                    onChange={handleFileSelect}
                                    className="hidden"
                                />
                                
                                {file ? (
                                    <div className="flex flex-col items-center gap-4">
                                        <FileXls size={48} weight="duotone" className="text-[#002FA7]" />
                                        <div className="text-center">
                                            <p className="font-semibold">{file.name}</p>
                                            <p className="text-sm text-gray-500">
                                                {(file.size / 1024).toFixed(1)} KB
                                            </p>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="flex flex-col items-center gap-4">
                                        <CloudArrowUp size={48} weight="duotone" className="text-gray-400" />
                                        <div className="text-center">
                                            <p className="font-semibold">Drop your Pipeline file here</p>
                                            <p className="text-sm text-gray-500">or click to browse</p>
                                        </div>
                                        <p className="text-xs text-gray-400">Supported: CSV, XLSX (Max 10MB)</p>
                                    </div>
                                )}
                            </div>

                            {/* Progress bar */}
                            {uploading && (
                                <div className="mt-6">
                                    <div className="flex justify-between text-sm mb-2">
                                        <span className="text-gray-600">Uploading & Validating...</span>
                                        <span className="font-semibold">{progress}%</span>
                                    </div>
                                    <div className="progress-bar">
                                        <div 
                                            className="progress-fill" 
                                            style={{ width: `${progress}%` }}
                                        ></div>
                                    </div>
                                </div>
                            )}

                            {/* Error message */}
                            {error && (
                                <div className="mt-6 flex items-start gap-3 bg-red-50 border border-red-200 p-4" data-testid="upload-error">
                                    <XCircle size={20} weight="fill" className="text-red-500 flex-shrink-0 mt-0.5" />
                                    <p className="text-red-700 text-sm">{error}</p>
                                </div>
                            )}

                            {/* Upload success result (before processing) */}
                            {result && !processing && !processResult && (
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="mt-6"
                                >
                                    <div className="flex items-start gap-3 bg-green-50 border border-green-200 p-4 mb-4" data-testid="upload-success">
                                        <CheckCircle size={20} weight="fill" className="text-green-500 flex-shrink-0 mt-0.5" />
                                        <div>
                                            <p className="text-green-700 font-semibold">{result.message}</p>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                                        <div className="stat-card">
                                            <p className="stat-value">{result.total_records}</p>
                                            <p className="stat-label">Total Records</p>
                                        </div>
                                        <div className="stat-card">
                                            <p className="stat-value text-green-600">{result.valid_records}</p>
                                            <p className="stat-label">Valid</p>
                                        </div>
                                        <div className="stat-card">
                                            <p className="stat-value text-yellow-600">{result.duplicate_records}</p>
                                            <p className="stat-label">Duplicates</p>
                                        </div>
                                        <div className="stat-card">
                                            <p className="stat-value text-red-600">{result.invalid_records}</p>
                                            <p className="stat-label">Invalid</p>
                                        </div>
                                    </div>

                                    {/* Schema Info */}
                                    {result.schema_info && (
                                        <div className="card bg-gray-50 mb-4">
                                            <p className="label-small mb-3">Detected Schema</p>
                                            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                                                <div>
                                                    <p className="text-gray-600">Status Column:</p>
                                                    <p className="font-semibold">{result.schema_info.status_column || 'Not found'}</p>
                                                </div>
                                                <div>
                                                    <p className="text-gray-600">Email Column:</p>
                                                    <p className="font-semibold">{result.schema_info.email_column || 'Not found'}</p>
                                                </div>
                                                <div>
                                                    <p className="text-gray-600">Phone Column:</p>
                                                    <p className="font-semibold">{result.schema_info.phone_column || 'Not found'}</p>
                                                </div>
                                            </div>
                                            {result.schema_info.status_values && result.schema_info.status_values.length > 0 && (
                                                <div className="mt-4">
                                                    <p className="text-gray-600 text-sm mb-2">Detected Status Values:</p>
                                                    <div className="flex flex-wrap gap-2">
                                                        {result.schema_info.status_values.map((status) => (
                                                            <span 
                                                                key={status}
                                                                className="px-3 py-1 bg-[#002FA7]/10 border border-[#002FA7]/20 text-sm font-medium text-[#002FA7]"
                                                            >
                                                                {status}
                                                            </span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {result.errors && result.errors.length > 0 && (
                                        <div className="mb-4 p-4 bg-yellow-50 border border-yellow-200">
                                            <div className="flex items-center gap-2 mb-2">
                                                <Warning size={18} weight="fill" className="text-yellow-600" />
                                                <p className="font-semibold text-yellow-800">Validation Errors</p>
                                            </div>
                                            <ul className="text-sm text-yellow-700 space-y-1">
                                                {result.errors.map((err, idx) => (
                                                    <li key={idx}>{err}</li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                </motion.div>
                            )}

                            {/* Upload button */}
                            {file && !uploading && !result && (
                                <button
                                    onClick={handleUpload}
                                    className="btn-primary w-full mt-6"
                                    data-testid="upload-submit-button"
                                >
                                    Upload Pipeline File
                                </button>
                            )}

                            {/* Back button */}
                            <button
                                onClick={handleGoBack}
                                className="w-full mt-4 flex items-center justify-center gap-2 px-4 py-3 border border-gray-300 font-bold text-sm uppercase tracking-wider hover:bg-gray-50"
                            >
                                <ArrowLeft size={18} weight="bold" />
                                Back to Step 1
                            </button>
                        </>
                    )}
                </motion.div>
            </div>
        </Layout>
    );
}
