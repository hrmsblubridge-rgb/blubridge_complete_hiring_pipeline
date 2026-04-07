import { useState, useCallback } from 'react';
import { Layout } from '../components/Layout';
import { motion } from 'framer-motion';
import { CloudArrowUp, FileXls, CheckCircle, XCircle, Warning, Info } from '@phosphor-icons/react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

export default function UploadPipeline() {
    const [file, setFile] = useState(null);
    const [dragging, setDragging] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');

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
            setError('');
        }
    };

    const handleUpload = async () => {
        if (!file) return;

        setUploading(true);
        setProgress(0);
        setError('');
        setResult(null);

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
            setFile(null);
        } catch (err) {
            setError(err.response?.data?.detail || 'Upload failed. Please try again.');
        } finally {
            setUploading(false);
        }
    };

    return (
        <Layout>
            <div className="max-w-3xl mx-auto">
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                >
                    <h1 className="heading-1 mb-2">Upload Pipeline Data</h1>
                    <p className="text-gray-500 mb-8">
                        Upload your recruitment pipeline data. The system will automatically detect columns and status values.
                    </p>

                    {/* Dynamic Schema Info */}
                    <div className="card mb-8 bg-blue-50 border-blue-200">
                        <div className="flex items-start gap-3">
                            <Info size={20} weight="fill" className="text-blue-600 flex-shrink-0 mt-0.5" />
                            <div>
                                <p className="font-semibold text-blue-900 mb-2">Dynamic Schema Detection</p>
                                <p className="text-sm text-blue-800 mb-3">
                                    The system will automatically detect and map your columns. Ensure your file has:
                                </p>
                                <ul className="text-sm text-blue-700 space-y-1">
                                    <li>• <strong>Email</strong> or <strong>Phone</strong> column (at least one required for matching)</li>
                                    <li>• <strong>Status</strong> column (auto-detected from values like shortlisted, rejected, scheduled, etc.)</li>
                                    <li>• All other columns will be stored and displayed dynamically</li>
                                    <li>• Status values are extracted automatically from your data</li>
                                </ul>
                            </div>
                        </div>
                    </div>

                    {/* Upload Zone */}
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
                                    <p className="font-semibold">Drop your file here</p>
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
                                <span className="text-gray-600">Uploading & Processing...</span>
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

                    {/* Success result */}
                    {result && (
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
                                <div className="card bg-gray-50">
                                    <p className="label-small mb-3">Detected Schema</p>
                                    <div className="grid grid-cols-2 gap-4 text-sm">
                                        <div>
                                            <p className="text-gray-600">Total Columns:</p>
                                            <p className="font-semibold">{result.schema_info.total_columns}</p>
                                        </div>
                                        <div>
                                            <p className="text-gray-600">Email Column:</p>
                                            <p className="font-semibold">{result.schema_info.email_column || 'Not found'}</p>
                                        </div>
                                        <div>
                                            <p className="text-gray-600">Phone Column:</p>
                                            <p className="font-semibold">{result.schema_info.phone_column || 'Not found'}</p>
                                        </div>
                                        <div>
                                            <p className="text-gray-600">Status Column:</p>
                                            <p className="font-semibold">{result.schema_info.status_column || 'Not found'}</p>
                                        </div>
                                        <div>
                                            <p className="text-gray-600">Name Column:</p>
                                            <p className="font-semibold">{result.schema_info.name_column || 'Not found'}</p>
                                        </div>
                                        <div>
                                            <p className="text-gray-600">Job Role Column:</p>
                                            <p className="font-semibold">{result.schema_info.job_role_column || 'Not found'}</p>
                                        </div>
                                    </div>

                                    {/* Status Values */}
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

                                    <div className="mt-4">
                                        <p className="text-gray-600 text-sm mb-2">All Columns:</p>
                                        <div className="flex flex-wrap gap-2">
                                            {result.schema_info.columns?.map((col) => (
                                                <span 
                                                    key={col}
                                                    className="px-2 py-1 bg-white border border-gray-200 text-xs font-medium"
                                                >
                                                    {col}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            )}

                            {result.errors && result.errors.length > 0 && (
                                <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200">
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
                    {file && !uploading && (
                        <button
                            onClick={handleUpload}
                            className="btn-primary w-full mt-6"
                            data-testid="upload-submit-button"
                        >
                            Upload File
                        </button>
                    )}
                </motion.div>
            </div>
        </Layout>
    );
}
