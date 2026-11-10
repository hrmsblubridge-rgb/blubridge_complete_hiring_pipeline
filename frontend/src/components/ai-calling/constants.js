export const COLS = [
    ['candidate_name', 'Name'], ['phone_number', 'Phone'], ['job_role', 'Role'], ['interview_date', 'Date'],
    ['interview_time', 'Time (HH)'], ['language', 'Language'], ['company_name', 'Company'],
    ['office_address', 'Office address'], ['approved_for_test_call', 'Sheet flag'],
];

export const CATEGORY_LABELS = {
    missing_field: 'Missing mandatory fields',
    invalid_phone: 'Invalid phone numbers',
    invalid_date: 'Invalid interview dates',
    invalid_time: 'Invalid interview times',
    invalid_language: 'Invalid language',
    invalid_value: 'Invalid YES/NO flag',
    example_row: 'Example rows',
    duplicate_in_file: 'Duplicates in file',
    duplicate_existing: 'Already imported',
};

export const READINESS = {
    ready_calling_disabled: ['Ready for test call', 'bg-teal-50 text-teal-800'],
    not_approved: ['Needs approval', 'bg-amber-100 text-amber-800'],
    opted_out: ['Opted out', 'bg-zinc-200 text-zinc-700'],
    interview_passed: ['Interview date passed', 'bg-rose-50 text-rose-700'],
};

export const CALLING_DISABLED_MSG = 'AI Calling will be enabled after Bolna API integration and testing are completed.';

export const inputCls = 'w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-teal-500';
