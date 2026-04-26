import { FormEvent, useState } from "react";

type ApiKeyFormProps = {
  fields: readonly string[];
  helpUrl?: string;
  busy: boolean;
  onCancel: () => void;
  onSave: (values: Record<string, string>) => Promise<void>;
};

export function ApiKeyForm({
  fields,
  helpUrl,
  busy,
  onCancel,
  onSave,
}: ApiKeyFormProps) {
  const [values, setValues] = useState<Record<string, string>>({});

  function formatFieldLabel(field: string): string {
    return field.replace(/_/g, " ");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSave(values);
  }

  return (
    <form className="mt-4 grid gap-3 rounded-3xl bg-white/70 p-4" onSubmit={handleSubmit}>
      {fields.map((field) => (
        <label className="grid gap-1 text-sm text-stone-700" key={field}>
          <span className="font-medium capitalize">{formatFieldLabel(field)}</span>
          <input
            className="rounded-2xl border border-stone-300 bg-white px-4 py-3 outline-none transition focus:border-teal-500"
            name={field}
            onChange={(event) => {
              setValues((current) => ({
                ...current,
                [field]: event.target.value,
              }));
            }}
            placeholder={`Enter ${formatFieldLabel(field)}`}
            required
            value={values[field] ?? ""}
          />
        </label>
      ))}
      <div className="flex flex-wrap items-center gap-3 pt-2">
        <button
          className="rounded-full bg-stone-950 px-5 py-2 text-sm font-semibold text-white transition hover:bg-stone-800 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={busy}
          type="submit"
        >
          {busy ? "Saving..." : "Save Credentials"}
        </button>
        <button
          className="rounded-full border border-stone-300 px-5 py-2 text-sm font-semibold text-stone-700 transition hover:border-stone-400"
          onClick={onCancel}
          type="button"
        >
          Cancel
        </button>
        {helpUrl ? (
          <a
            className="text-sm font-semibold text-teal-700 underline-offset-4 hover:underline"
            href={helpUrl}
            rel="noreferrer"
            target="_blank"
          >
            How to find these values
          </a>
        ) : null}
      </div>
    </form>
  );
}
