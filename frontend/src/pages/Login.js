import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { motion } from 'framer-motion';
import { Eye, EyeSlash } from '@phosphor-icons/react';

export default function Login() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const { login } = useAuth();
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        const result = await login(username, password);
        
        if (result.success) {
            navigate('/home', { replace: true });
        } else {
            setError(result.error);
        }
        
        setLoading(false);
    };

    return (
        <div className="min-h-screen bg-[#f3f1e9] flex flex-col" data-testid="login-page">
            <header className="bg-[#efede5] border-b border-gray-300 py-4 px-6 flex justify-center">
                <img src="/blubridge-logo.webp" alt="Blubridge" />
            </header>
            <div className="flex-1 flex items-center justify-center p-4">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4 }}
                    className="w-full max-w-md"
                >
                    <div className="bg-[#fffdf7] rounded-xl shadow-sm overflow-hidden">
                        <div className="bg-[#1a2332] h-3 rounded-t-xl"></div>
                        <div className="p-8">
                            <h1 className="text-2xl font-bold text-gray-900 text-center mb-2" style={{fontFamily:'serif'}}>Welcome Back</h1>
                            <p className="text-gray-500 text-center text-sm mb-8">Sign in to access your analytics dashboard</p>

                            {error && (
                                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 mb-6 text-sm rounded" data-testid="login-error">
                                    {error}
                                </div>
                            )}

                            <form onSubmit={handleSubmit} className="space-y-5">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Username</label>
                                    <input
                                        type="text"
                                        value={username}
                                        onChange={(e) => setUsername(e.target.value)}
                                        className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-4 py-3 text-sm focus:outline-none focus:border-blue-400 focus:bg-white"
                                        placeholder="admin"
                                        required
                                        data-testid="username-input"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Password</label>
                                    <div className="relative">
                                        <input
                                            type={showPassword ? 'text' : 'password'}
                                            value={password}
                                            onChange={(e) => setPassword(e.target.value)}
                                            className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-4 py-3 pr-12 text-sm focus:outline-none focus:border-blue-400 focus:bg-white"
                                            placeholder="••••••••"
                                            required
                                            data-testid="password-input"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setShowPassword(!showPassword)}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                                        >
                                            {showPassword ? <EyeSlash size={20} /> : <Eye size={20} />}
                                        </button>
                                    </div>
                                </div>

                                <button
                                    type="submit"
                                    disabled={loading}
                                    className="w-full py-3 bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-bold rounded-lg disabled:opacity-50 tracking-wide flex items-center justify-center gap-2"
                                    data-testid="login-submit-btn"
                                >
                                    {loading ? (
                                        <>
                                            <div className="spinner w-5 h-5 border-white border-t-transparent"></div>
                                            Signing in...
                                        </>
                                    ) : (
                                        'Sign In'
                                    )}
                                </button>
                            </form>

                            <div className="mt-6 text-center text-xs text-gray-500">
                                <p>Default credentials: <code className="bg-gray-100 px-2 py-1 rounded">Admin User / Admin User</code></p>
                            </div>
                        </div>
                    </div>
                </motion.div>
            </div>
            <footer className="py-4 text-center text-sm text-gray-500">Copyright 2026 &copy; <b>Blubridge.com</b></footer>
        </div>
    );
}
