import { useId, useState } from "react";
import { FileSpreadsheet, UploadCloud, CheckCircle2, X } from "lucide-react";

// Dropzone de XLS com estados: vazio, arrastando, com arquivo.
export default function FileUpload({ label, hint, accept = ".xls,.xlsx", onChange, file, obrigatorio }) {
  const id = useId();
  const [arrastando, setArrastando] = useState(false);

  function pegaArquivo(lista) {
    onChange?.(lista?.[0] ?? null);
  }

  return (
    <div>
      <label
        htmlFor={id}
        onDragOver={(e) => {
          e.preventDefault();
          setArrastando(true);
        }}
        onDragLeave={() => setArrastando(false)}
        onDrop={(e) => {
          e.preventDefault();
          setArrastando(false);
          pegaArquivo(e.dataTransfer.files);
        }}
        className={[
          "group flex cursor-pointer flex-col gap-3 rounded-2xl border p-5 transition-all duration-200",
          file
            ? "border-jade-300 bg-jade-50/60"
            : arrastando
            ? "border-jade-400 bg-jade-50 shadow-panel"
            : "border-dashed border-slate-300 bg-white hover:border-jade-400 hover:bg-jade-50/30",
        ].join(" ")}
      >
        <div className="flex items-start justify-between gap-3">
          <span className="text-sm font-600 text-ink-800">
            {label}
            {obrigatorio && <span className="ml-1 text-signal-600">*</span>}
          </span>
          <span
            className={[
              "grid h-9 w-9 shrink-0 place-items-center rounded-lg transition-colors",
              file ? "bg-jade-600 text-white" : "bg-slate-100 text-slate-400 group-hover:bg-jade-100 group-hover:text-jade-600",
            ].join(" ")}
          >
            {file ? <CheckCircle2 className="h-5 w-5" /> : <UploadCloud className="h-5 w-5" />}
          </span>
        </div>

        {file ? (
          <div className="flex items-center gap-2.5 rounded-xl border border-jade-200 bg-white px-3 py-2.5">
            <FileSpreadsheet className="h-5 w-5 shrink-0 text-jade-600" />
            <span className="truncate text-sm font-500 text-ink-800">{file.name}</span>
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                onChange?.(null);
              }}
              className="ml-auto rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-signal-600"
              aria-label="Remover arquivo"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <p className="text-xs leading-relaxed text-slate-500">
            {hint ?? "Arraste o arquivo aqui ou clique para selecionar."}
            <span className="mt-1 block text-slate-400">Formatos aceitos: .xls, .xlsx</span>
          </p>
        )}

        <input
          id={id}
          type="file"
          accept={accept}
          onChange={(e) => pegaArquivo(e.target.files)}
          className="sr-only"
        />
      </label>
    </div>
  );
}
