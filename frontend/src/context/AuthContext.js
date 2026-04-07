import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

const API = process.env.REACT_APP_BACKEND_URL;

// Helper to format API error messages
function formatApiErrorDetail(detail) {
    if (detail == null) return "Something went wrong. Please try again.";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail))
        return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
    if (detail && typeof detail.msg === "string") return detail.msg;
    return String(detail);
}

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null); // null = checking, false = not authenticated
    const [loading, setLoading] = useState(true);

    const checkAuth = useCallback(async () => {
        try {
            const response = await axios.get(`${API}/api/auth/me`, {
                withCredentials: true
            });
            setUser(response.data);
        } catch (error) {
            // Try to refresh token
            try {
                await axios.post(`${API}/api/auth/refresh`, {}, {
                    withCredentials: true
                });
                const response = await axios.get(`${API}/api/auth/me`, {
                    withCredentials: true
                });
                setUser(response.data);
            } catch {
                setUser(false);
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        checkAuth();
    }, [checkAuth]);

    const login = async (email, password) => {
        try {
            const response = await axios.post(`${API}/api/auth/login`, {
                email,
                password
            }, {
                withCredentials: true
            });
            setUser(response.data);
            return { success: true };
        } catch (error) {
            return {
                success: false,
                error: formatApiErrorDetail(error.response?.data?.detail) || error.message
            };
        }
    };

    const register = async (name, email, password) => {
        try {
            const response = await axios.post(`${API}/api/auth/register`, {
                name,
                email,
                password
            }, {
                withCredentials: true
            });
            setUser(response.data);
            return { success: true };
        } catch (error) {
            return {
                success: false,
                error: formatApiErrorDetail(error.response?.data?.detail) || error.message
            };
        }
    };

    const logout = async () => {
        try {
            await axios.post(`${API}/api/auth/logout`, {}, {
                withCredentials: true
            });
        } catch (error) {
            console.error('Logout error:', error);
        } finally {
            setUser(false);
        }
    };

    return (
        <AuthContext.Provider value={{ user, loading, login, register, logout, checkAuth }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
