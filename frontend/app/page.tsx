"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API = (
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

type ValidationIssue = {
  code?: string;
  field?: string;
  message: string;
};

type Invoice = {
  id: number;
  filename: string;
  status: string;
  extracted: Record<string, any>;
  validation?: {
    valid?: boolean;
    errors?: ValidationIssue[];
    warnings?: ValidationIssue[];
  };
  heuristic_score: number;
};

const fields = [
  "vendor_name",
  "vendor_tax_id",
  "invoice_number",
  "invoice_date",
  "due_date",
  "currency",
  "subtotal",
  "tax",
  "total",
];

const buttonStyle: React.CSSProperties = {
  border: 0,
  background: "#3348bd",
  color: "white",
  padding: "10px 13px",
  borderRadius: 8,
  cursor: "pointer",
};

const inputStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  boxSizing: "border-box",
  padding: 10,
  marginTop: 4,
  border: "1px solid #cbd5e1",
  borderRadius: 7,
  color: "#172033",
  background: "white",
};

export default function Home() {
  const [rows, setRows] = useState<Invoice[]>([]);
  const [selected, setSelected] = useState<Invoice | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch the invoice list without depending on selected invoice state.
  // This prevents the refresh effect from repeatedly triggering itself.
  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API}/documents`, {
        cache: "no-store",
      });

      if (!res.ok) {
        throw new Error(`API returned HTTP ${res.status}`);
      }

      const data: Invoice[] = await res.json();
      setRows(data);

      setSelected((current) => {
        if (!current) return current;

        return data.find((invoice) => invoice.id === current.id) ?? current;
      });

      return data;
    } catch (error) {
      console.error("Invoice list refresh failed:", error);
      setMessage(
        `Could not load invoices: ${String(error)}. Check that FastAPI is running at ${API}.`
      );
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // Load once on mount. Do not poll continuously.
  useEffect(() => {
    void refresh();
  }, [refresh]);

  function choose(invoice: Invoice) {
    setSelected(invoice);

    setDraft(
      Object.fromEntries(
        fields.map((field) => [
          field,
          invoice.extracted?.[field] == null
            ? ""
            : String(invoice.extracted[field]),
        ])
      )
    );
  }

  async function readResponse(res: Response) {
    const text = await res.text();

    if (!text) return {};

    try {
      return JSON.parse(text);
    } catch {
      return { detail: text };
    }
  }

  async function upload(file?: File) {
    console.log("UPLOAD HANDLER CALLED:", file?.name);

    if (!file) {
      setMessage("No file selected. Please choose an invoice file.");
      return;
    }

    if (busy) return;

    setBusy(true);
    setMessage(`Uploading ${file.name}…`);

    const form = new FormData();
    form.append("file", file);

    try {
      console.log("SENDING UPLOAD REQUEST:", `${API}/documents`);

      const res = await fetch(`${API}/documents`, {
        method: "POST",
        body: form,
      });

      console.log("UPLOAD RESPONSE STATUS:", res.status);

      const payload = await readResponse(res);
      console.log("UPLOAD RESPONSE BODY:", payload);

      if (!res.ok) {
        const detail =
          typeof payload.detail === "string"
            ? payload.detail
            : JSON.stringify(payload.detail ?? payload);

        throw new Error(detail || `Upload failed with HTTP ${res.status}`);
      }

      const invoice = payload.invoice as Invoice | undefined;

      setMessage(
        payload.duplicate_upload
          ? "This exact file was already uploaded."
          : "Upload completed. Checking extracted invoice fields…"
      );

      const latestRows = await refresh();

      if (invoice) {
        choose(invoice);
      } else if (latestRows?.length) {
        const latest = [...latestRows].sort((a, b) => b.id - a.id)[0];
        if (latest) choose(latest);
      }

      if (invoice && !invoice.extracted?.vendor_name && !invoice.extracted?.total) {
        setMessage(
          "File uploaded, but important invoice fields are missing. Review the validation errors before approval."
        );
      }
    } catch (error) {
      console.error("Invoice upload failed:", error);
      setMessage(`Upload failed: ${String(error)}`);
    } finally {
      setBusy(false);

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  async function act(
    path: string,
    body?: unknown,
    method = "POST"
  ) {
    if (!selected || busy) return;

    setBusy(true);
    setMessage("Processing request…");

    try {
      const res = await fetch(`${API}${path}`, {
        method,
        headers: {
          "Content-Type": "application/json",
          "X-Reviewer": "local-reviewer",
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });

      const payload = await readResponse(res);

      if (!res.ok) {
        const detail =
          typeof payload.detail === "string"
            ? payload.detail
            : JSON.stringify(payload.detail ?? payload);

        throw new Error(detail || `Request failed with HTTP ${res.status}`);
      }

      const latestRows = await refresh();

      if (payload.invoice) {
        choose(payload.invoice as Invoice);
      } else if (payload.id) {
        choose(payload as Invoice);
      } else if (latestRows) {
        const updated = latestRows.find(
          (invoice) => invoice.id === selected.id
        );
        if (updated) choose(updated);
      }

      setMessage("Request completed successfully.");
    } catch (error) {
      console.error("Invoice action failed:", error);
      setMessage(`Action failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main
      style={{
        maxWidth: 1200,
        margin: "0 auto",
        padding: 28,
        color: "#172033",
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div>
          <p style={{ color: "#586780", marginBottom: 4 }}>
            HUMAN-IN-THE-LOOP OPERATIONS
          </p>
          <h1 style={{ margin: 0 }}>InvoiceAI Review Desk</h1>
          <p style={{ color: "#586780" }}>
            Extract → validate → review → approve → sync
          </p>
        </div>

        <button
          type="button"
          disabled={busy}
          onClick={() => fileInputRef.current?.click()}
          style={{
            ...buttonStyle,
            background: "#172033",
            padding: "12px 16px",
            opacity: busy ? 0.65 : 1,
          }}
        >
          {busy ? "Working…" : "Upload document"}
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp,.txt,.eml"
          disabled={busy}
          onChange={(event) => {
            const file = event.currentTarget.files?.[0];
            void upload(file);
          }}
          style={{ display: "none" }}
        />
      </header>

      {message && (
        <p
          role="status"
          aria-live="polite"
          style={{
            padding: 12,
            background: "white",
            border: "1px solid #e2e8f0",
            borderRadius: 8,
            overflowWrap: "anywhere",
          }}
        >
          {message}
        </p>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(260px, 0.8fr) minmax(360px, 1.4fr)",
          gap: 18,
          marginTop: 18,
        }}
      >
        <section
          style={{
            background: "white",
            padding: 18,
            borderRadius: 14,
            border: "1px solid #e2e8f0",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 8,
            }}
          >
            <h2 style={{ marginTop: 0 }}>Documents ({rows.length})</h2>

            <button
              type="button"
              disabled={loading || busy}
              onClick={() => void refresh()}
              style={{
                ...buttonStyle,
                background: "#64748b",
                padding: "7px 10px",
              }}
            >
              Refresh
            </button>
          </div>

          {loading && <p>Loading invoices…</p>}

          {!loading && rows.length === 0 && (
            <p style={{ color: "#64748b" }}>
              No documents yet. Upload a sample invoice to begin.
            </p>
          )}

          {rows.map((row) => (
            <button
              key={row.id}
              type="button"
              onClick={() => choose(row)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: 12,
                marginBottom: 8,
                borderRadius: 8,
                border:
                  selected?.id === row.id
                    ? "2px solid #5267df"
                    : "1px solid #e2e8f0",
                background: "white",
                color: "#172033",
                cursor: "pointer",
              }}
            >
              <strong>
                #{row.id} · {row.extracted?.vendor_name || row.filename}
              </strong>
              <br />
              <small>
                {row.extracted?.invoice_number || "No invoice number"} ·{" "}
                {row.status}
              </small>
            </button>
          ))}
        </section>

        <section
          style={{
            background: "white",
            padding: 18,
            borderRadius: 14,
            border: "1px solid #e2e8f0",
            minWidth: 0,
          }}
        >
          {!selected ? (
            <>
              <h2 style={{ marginTop: 0 }}>Review details</h2>
              <p style={{ color: "#64748b" }}>
                Select an invoice to inspect fields and validation results.
              </p>
            </>
          ) : (
            <>
              <h2 style={{ marginTop: 0 }}>Invoice #{selected.id}</h2>

              <p>
                <strong>Status:</strong> {selected.status} ·{" "}
                <strong>Completeness score:</strong>{" "}
                {((selected.heuristic_score ?? 0) * 100).toFixed(0)}%
              </p>

              <p style={{ color: "#64748b", fontSize: 13 }}>
                Completeness is not calibrated model confidence. Verify every
                field before approval.
              </p>

              {(selected.validation?.errors ?? []).map((error, index) => (
                <p
                  key={index}
                  style={{
                    background: "#fff1f0",
                    padding: 10,
                    borderRadius: 6,
                    overflowWrap: "anywhere",
                  }}
                >
                  Error · {error.field || error.code}: {error.message}
                </p>
              ))}

              {(selected.validation?.warnings ?? []).map((warning, index) => (
                <p
                  key={index}
                  style={{
                    background: "#fff8e6",
                    padding: 10,
                    borderRadius: 6,
                    overflowWrap: "anywhere",
                  }}
                >
                  Warning · {warning.message}
                </p>
              ))}

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                  gap: 12,
                }}
              >
                {fields.map((field) => (
                  <label
                    key={field}
                    style={{
                      display: "block",
                      fontSize: 13,
                      color: "#475569",
                    }}
                  >
                    {field.replaceAll("_", " ")}
                    <input
                      value={draft[field] ?? ""}
                      onChange={(event) =>
                        setDraft((current) => ({
                          ...current,
                          [field]: event.target.value,
                        }))
                      }
                      style={inputStyle}
                    />
                  </label>
                ))}
              </div>

              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 8,
                  marginTop: 18,
                }}
              >
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void act(
                      `/reviews/${selected.id}`,
                      {
                        corrected_fields: Object.fromEntries(
                          Object.entries(draft).map(([key, value]) => [
                            key,
                            value === "" ? null : value,
                          ])
                        ),
                        notes: "Updated in review UI",
                      },
                      "PATCH"
                    )
                  }
                  style={buttonStyle}
                >
                  Save corrections
                </button>

                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void act(`/reviews/${selected.id}/approve`, {
                      notes: "Reviewed in UI",
                    })
                  }
                  style={{
                    ...buttonStyle,
                    opacity: busy ? 0.65 : 1,
                  }}
                >
                  Approve
                </button>

                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void act(`/reviews/${selected.id}/reject`, {
                      notes: "Rejected in UI",
                    })
                  }
                  style={{
                    ...buttonStyle,
                    background: "#9f2d38",
                  }}
                >
                  Reject
                </button>

                <button
                  type="button"
                  disabled={busy || selected.status !== "approved"}
                  onClick={() =>
                    void act(`/integrations/quickbooks/sync/${selected.id}`)
                  }
                  style={{
                    ...buttonStyle,
                    opacity:
                      busy || selected.status !== "approved" ? 0.55 : 1,
                  }}
                >
                  Sync QuickBooks
                </button>
              </div>
            </>
          )}
        </section>
      </div>

      <footer
        style={{
          color: "#64748b",
          fontSize: 12,
          marginTop: 20,
        }}
      >
        Development UI only. Add production authentication, reviewer roles,
        tenant isolation, and secure document storage before deployment.
      </footer>
    </main>
  );
}