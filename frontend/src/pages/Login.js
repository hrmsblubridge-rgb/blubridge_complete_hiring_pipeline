import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { motion } from 'framer-motion';
import { Eye, EyeSlash, ChartBar } from '@phosphor-icons/react';

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
            navigate('/dashboard', { replace: true });
        } else {
            setError(result.error);
        }
        
        setLoading(false);
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-[#F9FAFB] p-4">
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
                className="w-full max-w-md"
            >
                <div className="bg-white border border-gray-200 p-8">
                    {/* Logo */}
                    <div className="flex items-center justify-center gap-2 mb-8">
                        <div className="w-12 h-12 bg-[#002FA7] flex items-center justify-center">
                            <ChartBar size={28} weight="bold" className="text-white" />
                        </div>
                        <span className="font-bold text-2xl tracking-tight">RECRUIT<span className="text-[#002FA7]">IQ</span></span>
                    </div>

                    <h1 className="heading-2 text-center mb-2">Welcome Back</h1>
                    <p className="text-gray-500 text-center mb-8">Sign in to access your analytics dashboard</p>

                    {error && (
                        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 mb-6 text-sm" data-testid="login-error">
                            {error}
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-6">
                        <div>
                            <label className="label-small block mb-2">Username</label>
                            <input
                                type="text"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                className="input w-full"
                                placeholder="admin"
                                required
                                data-testid="username-input"
                            />
                        </div>

                        <div>
                            <label className="label-small block mb-2">Password</label>
                            <div className="relative">
                                <input
                                    type={showPassword ? 'text' : 'password'}
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="input w-full pr-12"
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
                            className="btn-primary w-full flex items-center justify-center gap-2"
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

                    <div className="mt-6 text-center text-sm text-gray-500">
                        <p>Default credentials: <code className="bg-gray-100 px-2 py-1">admin / admin</code></p>
                    </div>
                </div>
            </motion.div>
        </div>
    );
}
