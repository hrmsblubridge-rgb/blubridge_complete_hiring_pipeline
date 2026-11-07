import axios from 'axios';

export const aiApi = axios.create({
    baseURL: `${process.env.REACT_APP_BACKEND_URL}/api/ai-calling`,
    withCredentials: true,
});

export const errMsg = (e, fallback = 'Request failed') => {
    const d = e?.response?.data?.detail;
    return typeof d === 'string' ? d : fallback;
};

export const MODE_STYLES = {
    off: 'bg-zinc-100 text-zinc-700 border-zinc-200',
    testing: 'bg-teal-50 text-teal-800 border-teal-200',
    live: 'bg-rose-50 text-rose-800 border-rose-200',
};
