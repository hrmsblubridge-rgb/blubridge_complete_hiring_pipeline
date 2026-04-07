import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { motion } from 'framer-motion';
import { Eye, EyeSlash, ChartBar } from '@phosphor-icons/react';

export default function Register() {
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const { register } = useAuth();
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        if (password !== confirmPassword) {
            setError('Passwords do not match');
            return;
        }

        if (password.length < 6) {
            setError('Password must be at least 6 characters');
            return;
        }

        setLoading(true);

        const result = await register(name, email, password);
        
        if (result.success) {
            navigate('/dashboard', { replace: true });
        } else {
            setError(result.error);
        }
        
        setLoading(false);
    };

    return (
        <div className="min-h-screen flex">
            {/* Left side - Image */}
            <div 
                className="hidden lg:block lg:w-1/2 bg-cover bg-center relative"
                style={{
                    backgroundImage: 'url(https://images.unsplash.com/photo-1765416589470-0ab68a9368e9?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NzF8MHwxfHNlYXJjaHwyfHxhYnN0cmFjdCUyMGFyY2hpdGVjdHVyYWwlMjBnZW9tZXRyaWMlMjBsaWdodCUyMHdoaXRlfGVufDB8fHx8MTc3NTU0MzEwNXww&ixlib=rb-4.1.0&q=85)'
                }}
            >
                <div className="absolute inset-0 bg-[#002FA7]/10"></div>
                <div className="absolute bottom-0 left-0 right-0 p-12 bg-gradient-to-t from-black/50 to-transparent">
                    <p className="text-white text-2xl font-bold leading-tight">
                        Join thousands of recruiters<br />making data-driven decisions
                    </p>
                </div>
            </div>

            {/* Right side - Form */}
            <div className="flex-1 flex items-center justify-center p-8 bg-white">
                <motion.div
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.4 }}
                    className="w-full max-w-md"
                >
                    {/* Logo */}
                    <div className="flex items-center gap-2 mb-12">
                        <div className="w-10 h-10 bg-[#002FA7] flex items-center justify-center">
                            <ChartBar size={24} weight="bold" className="text-white" />
                        </div>
                        <span className="font-bold text-xl tracking-tight">RECRUIT<span className="text-[#002FA7]">IQ</span></span>
                    </div>

                    <h1 className="heading-1 mb-2">Create account</h1>
                    <p className="text-gray-500 mb-8">Start analyzing your recruitment funnel today</p>

                    {error && (
                        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 mb-6 text-sm" data-testid="register-error">
                            {error}
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-5">
                        <div>
                            <label className="label-small block mb-2">Full Name</label>
                            <input
                                type="text"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                className="input w-full"
                                placeholder="John Doe"
                                required
                                data-testid="name-input"
                            />
                        </div>

                        <div>
                            <label className="label-small block mb-2">Email</label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="input w-full"
                                placeholder="you@company.com"
                                required
                                data-testid="email-input"
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
                                    minLength={6}
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

                        <div>
                            <label className="label-small block mb-2">Confirm Password</label>
                            <input
                                type={showPassword ? 'text' : 'password'}
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                className="input w-full"
                                placeholder="••••••••"
                                required
                                data-testid="confirm-password-input"
                            />
                        </div>

                        <button
                            type="submit"
                            disabled={loading}
                            className="btn-primary w-full flex items-center justify-center gap-2"
                            data-testid="register-form-submit-button"
                        >
                            {loading ? (
                                <>
                                    <div className="spinner w-5 h-5 border-white border-t-transparent"></div>
                                    Creating account...
                                </>
                            ) : (
                                'Create Account'
                            )}
                        </button>
                    </form>

                    <p className="mt-8 text-center text-gray-500">
                        Already have an account?{' '}
                        <Link to="/login" className="text-[#002FA7] font-semibold hover:underline">
                            Sign in
                        </Link>
                    </p>
                </motion.div>
            </div>
        </div>
    );
}
