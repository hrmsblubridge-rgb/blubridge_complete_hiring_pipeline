import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ChartBar, Upload, SignOut, User } from '@phosphor-icons/react';
import { motion } from 'framer-motion';

export function Layout({ children }) {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = async () => {
        await logout();
        navigate('/login');
    };

    const navItems = [
        { to: '/dashboard', label: 'Dashboard', icon: ChartBar },
        { to: '/upload/naukri', label: 'Upload Naukri', icon: Upload },
        { to: '/upload/pipeline', label: 'Upload Pipeline', icon: Upload },
    ];

    return (
        <div className="min-h-screen bg-[#F9FAFB]">
            {/* Header */}
            <header className="bg-white border-b border-gray-200">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between h-16">
                        {/* Logo */}
                        <div className="flex items-center gap-8">
                            <NavLink to="/dashboard" className="flex items-center gap-2">
                                <div className="w-8 h-8 bg-[#002FA7] flex items-center justify-center">
                                    <ChartBar size={20} weight="bold" className="text-white" />
                                </div>
                                <span className="font-bold text-lg tracking-tight">RECRUIT<span className="text-[#002FA7]">IQ</span></span>
                            </NavLink>

                            {/* Navigation */}
                            <nav className="hidden md:flex items-center gap-6">
                                {navItems.map((item) => (
                                    <NavLink
                                        key={item.to}
                                        to={item.to}
                                        className={({ isActive }) =>
                                            `nav-link flex items-center gap-2 text-sm ${isActive ? 'active' : ''}`
                                        }
                                    >
                                        <item.icon size={18} weight="bold" />
                                        {item.label}
                                    </NavLink>
                                ))}
                            </nav>
                        </div>

                        {/* User menu */}
                        <div className="flex items-center gap-4">
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
                    {navItems.map((item) => (
                        <NavLink
                            key={item.to}
                            to={item.to}
                            className={({ isActive }) =>
                                `nav-link flex items-center gap-2 text-sm whitespace-nowrap ${isActive ? 'active' : ''}`
                            }
                        >
                            <item.icon size={16} weight="bold" />
                            {item.label}
                        </NavLink>
                    ))}
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
