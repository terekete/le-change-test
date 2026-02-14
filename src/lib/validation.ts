export const validateEmail = (email: string): boolean => /^[^@]+@[^@]+\.[^@]+$/.test(email);
