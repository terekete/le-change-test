export const Button = ({ label, onClick }: { label: string; onClick?: () => void }) => <button onClick={onClick}>{label}</button>;
