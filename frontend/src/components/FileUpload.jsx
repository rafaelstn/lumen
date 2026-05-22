// Campo de upload de arquivo XLS. Lógica de submit completa na Fase 6.
export default function FileUpload({ label, accept = ".xls,.xlsx", onChange, file }) {
  return (
    <label className="block border border-dashed border-slate-300 rounded-lg p-4 cursor-pointer hover:border-slate-400 transition">
      <span className="block text-sm font-medium text-slate-700 mb-2">{label}</span>
      <input
        type="file"
        accept={accept}
        onChange={(e) => onChange?.(e.target.files?.[0] ?? null)}
        className="text-sm"
      />
      {file && <span className="block mt-2 text-xs text-slate-500">{file.name}</span>}
    </label>
  );
}
