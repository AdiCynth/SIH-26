type LabelProps = React.LabelHTMLAttributes<HTMLLabelElement>;

export default function Label({ className = "", children, ...props }: LabelProps) {
  return (
    <label
      className={`text-[12px] font-medium text-text-secondary ${className}`}
      {...props}
    >
      {children}
    </label>
  );
}
