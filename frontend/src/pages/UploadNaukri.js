import { useState, useCallback } from 'react';
import { Layout } from '../components/Layout';
import { motion } from 'framer-motion';
import { CloudArrowUp, FileXls, CheckCircle, XCircle, Warning } from '@phosphor-icons/react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

export default function UploadNaukri() {
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
            const response = await axios.post(`${API}/api/upload/naukri`, formData, {
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
                    <h1 className="heading-1 mb-2">Upload Naukri Applies</h1>
                    <p className="text-gray-500 mb-8">
                        Upload your Naukri job applications data. Supported formats: CSV, XLSX
                    </p>

                    {/* Required columns info */}
                    <div className="card mb-8">
                        <p className="label-small">Required Columns</p>
                        <div className="flex flex-wrap gap-2 mt-2">
                            {['Name', 'Email', 'Phone Number', 'Job Role'].map((col) => (
                                <span 
                                    key={col}
                                    className="px-3 py-1 bg-gray-100 border border-gray-200 text-sm font-medium"
                                >
                                    {col}
                                </span>
                            ))}
                        </div>
                    </div>

                    {/* Upload Zone */}
                    <div
                        className={`upload-zone ${dragging ? 'dragging' : ''}`}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        onClick={() => document.getElementById('file-input').click()}
                        data-testid="upload-naukri-input"
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
                                <p className="text-xs text-gray-400">Maximum file size: 10MB</p>
                            </div>
                        )}
                    </div>

                    {/* Progress bar */}
                    {uploading && (
                        <div className="mt-6">
                            <div className="flex justify-between text-sm mb-2">
                                <span className="text-gray-600">Uploading...</span>
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

                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
