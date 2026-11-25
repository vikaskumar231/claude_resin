"use client";
import { useState } from "react";
type Enq = { id: string; reference_code: string; product_name_snapshot?: string; customer_name?: string; whatsapp_number: string;
  requirements: string; needed_by?: string; reason?: string; status: string; created_at: string };
const STATUSES = ["new", "contacted", "in_discussion", "won", "closed", "spam"];
export default function Admin() {
  const [csrf, setCsrf] = useState(""); const [rows, setRows] = useState<Enq[]>([]); const [err, setErr] = useState("");
  const call = (p: string, o: RequestInit = {}) => fetch(`/backend${p}`, { ...o, headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, ...(o.headers || {}) } });
  async function load(token = csrf) {
    const r = await fetch("/backend/admin/enquiries", { headers: { "X-CSRF-Token": token } });
    if (r.ok) setRows(await r.json()); else setErr("Session expired. Please sign in again.");
  }
  async function login(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget);
    const r = await fetch("/backend/admin/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: f.get("email"), password: f.get("password") }) });
    if (!r.ok) return setErr("Invalid credentials or account locked");
    const { csrf: t } = await r.json(); setCsrf(t); setErr(""); load(t);
  }
  async function setStatus(id: string, status: string) { await call(`/admin/enquiries/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }); load(); }
  async function del(id: string) { if (confirm("Delete this enquiry and its personal data?")) { await call(`/admin/enquiries/${id}`, { method: "DELETE" }); load(); } }
  if (!csrf) return (<form className="enq" onSubmit={login}><h1>Admin sign in</h1><input name="email" type="email" placeholder="Email" required/>
    <input name="password" type="password" placeholder="Password" required/>{err && <p>{err}</p>}<button className="btn">Sign in</button></form>);
  return (<><h1>Enquiries ({rows.filter(r => r.status === "new").length} new)</h1>{err && <p>{err}</p>}
    <div style={{overflowX:"auto"}}><table><thead><tr><th>Ref</th><th>Product</th><th>Details</th><th>Status</th><th></th></tr></thead><tbody>
      {rows.map(r => (<tr key={r.id}><td>{r.reference_code}<br/><span className="muted">{new Date(r.created_at).toLocaleDateString()}</span></td>
        <td>{r.product_name_snapshot || "Custom idea"}</td>
        <td><b>{r.whatsapp_number}</b> {r.customer_name}<br/>{r.requirements}{r.needed_by && <><br/>Needed by {r.needed_by}</>}{r.reason && <><br/>Why: {r.reason}</>}</td>
        <td><select value={r.status} onChange={e => setStatus(r.id, e.target.value)}>{STATUSES.map(s => <option key={s}>{s}</option>)}</select></td>
        <td><a className="btn" target="_blank" rel="noopener" href={`https://wa.me/${r.whatsapp_number.replace("+", "")}?text=${encodeURIComponent(`Hi${r.customer_name ? " " + r.customer_name : ""}, this is Artआलय about your enquiry ${r.reference_code}.`)}`}>Reply</a>
          <button className="btn alt" onClick={() => del(r.id)}>Delete</button></td></tr>))}</tbody></table></div></>);
}
