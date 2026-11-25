"use client";
import { useEffect, useState } from "react";
type Enq = { id: string; reference_code: string; product_name_snapshot?: string; customer_name?: string; whatsapp_number: string;
  requirements: string; needed_by?: string; reason?: string; status: string; created_at: string };
type Prod = { id: string; slug: string; name: string; status: string; starting_price_inr: string | null; cover_media_id?: string; category: string };
type Cat = { slug: string; name: string; is_active: boolean };
type Tag = { slug: string; label: string };
const STATUSES = ["new", "contacted", "in_discussion", "won", "closed", "spam"];
const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") + "-" + Math.random().toString(36).slice(2, 6);

export default function Admin() {
  const [csrf, setCsrf] = useState(""); const [tab, setTab] = useState("enquiries"); const [err, setErr] = useState(""); const [msg, setMsg] = useState("");
  const [enqs, setEnqs] = useState<Enq[]>([]); const [prods, setProds] = useState<Prod[]>([]); const [cats, setCats] = useState<Cat[]>([]); const [tags, setTags] = useState<Tag[]>([]);
  // The CSRF token lives only in memory; the httpOnly session cookie restores it after a reload.
  const call = (p: string, o: RequestInit = {}, t = csrf) => fetch(`/backend${p}`, { ...o, headers: { "Content-Type": "application/json", "X-CSRF-Token": t, ...(o.headers || {}) } });
  async function loadAll(t = csrf) {
    const g = async (p: string) => { const r = await call(p, {}, t); return r.ok ? r.json() : []; };
    setEnqs(await g("/admin/enquiries")); setProds(await g("/admin/products")); setCats(await g("/admin/categories")); setTags(await g("/admin/tags"));
  }
  useEffect(() => { fetch("/backend/admin/me").then(async r => { if (r.ok) { const j = await r.json(); setCsrf(j.csrf); loadAll(j.csrf); } }); }, []);
  async function login(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget);
    const r = await fetch("/backend/admin/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: f.get("email"), password: f.get("password") }) });
    if (!r.ok) return setErr("Invalid credentials or account locked");
    const { csrf: t } = await r.json(); setCsrf(t); setErr(""); loadAll(t);
  }
  const act = async (p: string, method: string, body?: object) => { const r = await call(p, { method, body: body && JSON.stringify(body) });
    if (!r.ok) setErr((await r.json().catch(() => ({}))).detail || "Something went wrong"); else { setErr(""); await loadAll(); } };

  async function addProduct(e: React.FormEvent<HTMLFormElement>, publish: boolean) {
    e.preventDefault(); const form = e.currentTarget.form ?? e.currentTarget; const f = new FormData(form as HTMLFormElement); setMsg("Uploading photos…");
    const ids: string[] = [];
    for (const file of f.getAll("photos") as File[]) {
      if (!file.size) continue; const u = new FormData(); u.append("file", file);
      const r = await fetch("/backend/admin/media", { method: "POST", headers: { "X-CSRF-Token": csrf }, body: u });
      if (!r.ok) { setMsg(""); return setErr(`Could not upload ${file.name}`); } ids.push((await r.json()).asset_id);
    }
    const price = String(f.get("price") || "").trim();
    const r = await call("/admin/products", { method: "POST", body: JSON.stringify({ category_slug: f.get("category"), name: f.get("name"), slug: slugify(String(f.get("name"))),
      short_description: f.get("short") || null, description: f.get("desc") || null, starting_price_inr: price ? Number(price) : null,
      publish, asset_ids: ids, tag_slugs: f.getAll("tags") }) });
    setMsg(""); if (!r.ok) return setErr((await r.json().catch(() => ({}))).detail || "Could not save the product");
    setErr(""); (form as HTMLFormElement).reset(); setMsg(publish ? "Published!" : "Saved as draft."); await loadAll(); setTab("products");
  }

  if (!csrf) return (<form className="enq" onSubmit={login}><h1>Admin sign in</h1><input name="email" type="email" placeholder="Email" required/>
    <input name="password" type="password" placeholder="Password" required/>{err && <p>{err}</p>}<button className="btn">Sign in</button></form>);

  return (<><div className="chips">{["enquiries", "products", "add", "categories"].map(t => <button key={t} className={`chip ${tab === t ? "on" : ""}`} style={{border:0,font:"inherit"}} onClick={() => setTab(t)}>
      {t === "enquiries" ? `Enquiries (${enqs.filter(r => r.status === "new").length} new)` : t === "add" ? "Add product" : t[0].toUpperCase() + t.slice(1)}</button>)}
    <button className="chip" style={{border:0,font:"inherit"}} onClick={async () => { await call("/admin/auth/logout", { method: "POST" }); setCsrf(""); }}>Sign out</button></div>
    {err && <p style={{color:"var(--coral)"}}>{err}</p>}{msg && <p>{msg}</p>}

    {tab === "enquiries" && <div style={{overflowX:"auto"}}><table><thead><tr><th>Ref</th><th>Product</th><th>Details</th><th>Status</th><th></th></tr></thead><tbody>
      {enqs.map(r => (<tr key={r.id}><td>{r.reference_code}<br/><span className="muted">{new Date(r.created_at).toLocaleDateString()}</span></td><td>{r.product_name_snapshot || "Custom idea"}</td>
        <td><b>{r.whatsapp_number}</b> {r.customer_name}<br/>{r.requirements}{r.needed_by && <><br/>Needed by {r.needed_by}</>}{r.reason && <><br/>Why: {r.reason}</>}</td>
        <td><select value={r.status} onChange={e => act(`/admin/enquiries/${r.id}`, "PATCH", { status: e.target.value })}>{STATUSES.map(s => <option key={s}>{s}</option>)}</select></td>
        <td><a className="btn" target="_blank" rel="noopener" href={`https://wa.me/${r.whatsapp_number.replace("+", "")}?text=${encodeURIComponent(`Hi${r.customer_name ? " " + r.customer_name : ""}, this is Artआलय about your enquiry ${r.reference_code}.`)}`}>Reply</a>{" "}
          <button className="btn alt" onClick={() => confirm("Delete this enquiry and its personal data?") && act(`/admin/enquiries/${r.id}`, "DELETE")}>Delete</button></td></tr>))}</tbody></table></div>}

    {tab === "products" && <div style={{overflowX:"auto"}}><table><thead><tr><th></th><th>Name</th><th>Category</th><th>Price</th><th>Status</th><th></th></tr></thead><tbody>
      {prods.map(p => (<tr key={p.id}><td>{p.cover_media_id && <img src={`/backend/media/${p.cover_media_id}/thumb`} width={56} height={56} style={{borderRadius:12}} alt=""/>}</td>
        <td>{p.name}</td><td>{p.category}</td>
        <td><input style={{width:100}} defaultValue={p.starting_price_inr ?? ""} placeholder="On request" onBlur={e => { const v = e.target.value.trim();
          if (v !== (p.starting_price_inr ?? "")) act(`/admin/products/${p.id}`, "PATCH", v ? { starting_price_inr: Number(v) } : { clear_price: true }); }}/></td>
        <td>{p.status}</td><td><button className="btn alt" onClick={() => act(`/admin/products/${p.id}`, "PATCH", { status: p.status === "published" ? "draft" : "published" })}>{p.status === "published" ? "Unpublish" : "Publish"}</button>{" "}
          <button className="btn alt" onClick={() => confirm(`Delete ${p.name}?`) && act(`/admin/products/${p.id}`, "DELETE")}>Delete</button></td></tr>))}</tbody></table></div>}

    {tab === "add" && <form className="enq">
      <label>Category<select name="category" required>{cats.map(c => <option key={c.slug} value={c.slug}>{c.name}</option>)}</select></label>
      <label>Name<input name="name" required/></label>
      <label>Starting price in ₹ (leave empty to show Price on request)<input name="price" inputMode="decimal"/></label>
      <label>Short description<input name="short" maxLength={160}/></label><label>Full description<textarea name="desc" rows={3}/></label>
      <label>Photos (plain background works best; the first is the cover)<input name="photos" type="file" accept="image/*" multiple/></label>
      <div>{tags.map(t => <label key={t.slug} style={{display:"inline-flex",gap:6,marginRight:14}}><input style={{width:20}} type="checkbox" name="tags" value={t.slug}/>{t.label}</label>)}</div>
      <div><button className="btn alt" onClick={e => addProduct(e as any, false)}>Save draft</button>{" "}<button className="btn" onClick={e => addProduct(e as any, true)}>Publish</button></div></form>}

    {tab === "categories" && <table><tbody>{cats.map(c => (<tr key={c.slug}><td>{c.name}</td><td>{c.is_active ? "Visible" : "Hidden"}</td>
      <td><button className="btn alt" onClick={() => act(`/admin/categories/${c.slug}`, "PATCH", { is_active: !c.is_active })}>{c.is_active ? "Hide" : "Show"}</button></td></tr>))}</tbody></table>}</>);
}
