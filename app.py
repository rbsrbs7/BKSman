import io, re, datetime as dt
from zoneinfo import ZoneInfo
import pandas as pd, streamlit as st
from sqlalchemy import create_engine, text
from PIL import Image

st.set_page_config(page_title="Reservas do Prédio", page_icon="🏢")
TIPOS = {"1C1S": (3, [23,37,52,58,61,63,65,66,67,68,76], "C+S"), "1C2S": (4, [26], "C+2S"),
         "1C": (2, [44,57,71,72,73,74,75,77,78,81,82,83,84,85,86], "C"), "2C": (4, [62,64], "C+C"), "2S": (2, [87,88], "S+S")}
APTOS = sorted(((str(n), t, TIPOS[t][0]) for t in TIPOS for n in TIPOS[t][1]), key=lambda a: int(a[0]))
COR = {"Booking": "#1b63d4", "Airbnb": "#c8286f", "Direto": "#1a8a4c"}
br = lambda s: "/".join(s.split("-")[::-1][:2]) if s else ""
agora = lambda: dt.datetime.now(ZoneInfo("America/Sao_Paulo"))
tlabel = lambda t: "Sem preferência" if not t else f"{TIPOS[t][2]} ({t})"

# ---------- banco ----------
@st.cache_resource
def eng(): return create_engine(st.secrets.get("db_url", "sqlite:///reservas.db"), pool_pre_ping=True)
def ex(sql, **p):
    with eng().begin() as c: c.execute(text(sql), p)
def q(sql, **p):
    with eng().connect() as c: return [dict(r._mapping) for r in c.execute(text(sql), p)]
@st.cache_resource
def init():
    pg = eng().dialect.name == "postgresql"
    pk = "SERIAL PRIMARY KEY" if pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ex(f"""CREATE TABLE IF NOT EXISTS reservas(id {pk}, nome TEXT, apto TEXT DEFAULT '', hosp INT DEFAULT 0,
        ini TEXT, fim TEXT, origem TEXT, uid TEXT DEFAULT '', cama TEXT DEFAULT '', cpf TEXT, zap TEXT,
        carro TEXT, foto {'BYTEA' if pg else 'BLOB'}, cin TEXT, chave TEXT)""")
    ex("CREATE TABLE IF NOT EXISTS acessos(email TEXT PRIMARY KEY, perfil TEXT, status TEXT)")
    return True
COLS = "id,nome,apto,hosp,ini,fim,origem,uid,cama,cpf,zap,carro,cin,chave"
def conflito(apto, s, e, ign=-1):
    return bool(q("SELECT 1 FROM reservas WHERE apto=:a AND id<>:i AND ini<:e AND :s<fim", a=apto, i=ign, s=s, e=e))
def sugerir(hosp, cama, s, e, ign=-1):
    L = [a for a in APTOS if a[2] >= hosp and not conflito(a[0], s, e, ign)]
    return sorted(L, key=lambda a: (a[1] != cama, a[2], int(a[0])))[:3]
def cpf_ok(c):
    c = re.sub(r"\D", "", c)
    if len(c) != 11 or len(set(c)) == 1: return False
    for t in (9, 10):
        s = sum(int(c[i]) * (t + 1 - i) for i in range(t))
        if (s * 10 % 11) % 10 != int(c[t]): return False
    return True
def mask_cpf(c): c = re.sub(r"\D", "", c); return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
def mask_zap(z):
    z = re.sub(r"\D", "", z); k = 7 if len(z) > 10 else 6
    return f"({z[:2]}) {z[2:k]}-{z[k:]}"
def reduz(f):
    im = Image.open(f).convert("RGB"); im.thumbnail((1280, 1280)); b = io.BytesIO()
    im.save(b, "JPEG", quality=70); return b.getvalue()

# ---------- acesso ----------
def email():
    if "auth" in st.secrets:
        if not st.user.is_logged_in:
            st.title("🏢 Reservas do Prédio"); st.button("Entrar com Google", on_click=st.login, type="primary"); st.stop()
        with st.sidebar: st.write(st.user.email); st.button("Sair", on_click=st.logout)
        return st.user.email.lower()
    return st.sidebar.text_input("E-mail (modo local)", "admin@local").lower()

@st.dialog("Devolvida chave ?")
def confirmar(r, h):
    st.write(f"Confirmar a devolução da chave de **{r['nome']}** (apto {r['apto']})? O apartamento será liberado.")
    a, b = st.columns(2)
    if b.button("Sim, devolvida", type="primary", use_container_width=True):
        ex("UPDATE reservas SET chave=:c, fim=CASE WHEN :h<fim THEN :h ELSE fim END WHERE id=:i",
           c=agora().strftime("%Y-%m-%dT%H:%M"), h=str(h), i=r["id"]); st.rerun()
    if a.button("Não", use_container_width=True): st.rerun()

def linha(r, rotulo, chave, acao):
    st.markdown(f"**{r['nome']}**  \n{r['origem']} · {'apto ' + r['apto'] if r['apto'] else 'sem apto'} · {r['hosp'] or 'a confirmar'}p · {br(r['ini'])}→{br(r['fim'])}")
    if st.button(rotulo, key=chave, use_container_width=True): acao(r)
    st.divider()

# ---------- porteiro ----------
def tab_checkin(h):
    ci = st.session_state.get("ci")
    if ci is not None: return form_ci(ci, h)
    if st.button("➕ Check-in sem reserva", type="primary", use_container_width=True): st.session_state.ci = 0; st.rerun()
    R = q(f"SELECT {COLS} FROM reservas WHERE cin IS NULL AND fim>:h ORDER BY ini,nome", h=str(h))
    def go(r): st.session_state.ci = r["id"]; st.rerun()
    for tit, L in (("Chegadas de hoje", [r for r in R if r["ini"] <= str(h)]), ("Próximas chegadas", [r for r in R if r["ini"] > str(h)])):
        st.subheader(tit)
        if not L: st.caption("Nenhuma.")
        for r in L: linha(r, "Check-in", f"ci{r['id']}", go)

def form_ci(ci, h):
    r = q(f"SELECT {COLS} FROM reservas WHERE id=:i", i=ci)[0] if ci else None
    st.subheader(f"Check-in: {r['nome']}" if r else "Check-in sem reserva")
    nome = st.text_input("Nome completo", r["nome"] if r else "")
    cpf = st.text_input("CPF", placeholder="000.000.000-00")
    zap = st.text_input("WhatsApp com DDD (obrigatório)", placeholder="(11) 99999-0000")
    hosp = st.number_input("Número de hóspedes", 1, 4, min(max((r or {}).get("hosp") or 1, 1), 4))
    saida = st.date_input("Data de saída", dt.date.fromisoformat(r["fim"]) if r else h + dt.timedelta(1), format="DD/MM/YYYY")
    cama = st.selectbox("Cama preferida (opcional)", [""] + list(TIPOS), format_func=tlabel, index=([""] + list(TIPOS)).index((r or {}).get("cama") or ""))
    st.markdown("**Foto do documento**")
    f1 = st.camera_input("Tirar foto"); f2 = st.file_uploader("Escolher da galeria", type=["jpg", "jpeg", "png"])
    st.markdown("**Automóvel (opcional)**")
    mod, cor, placa = st.text_input("Modelo"), st.text_input("Cor"), st.text_input("Placa")
    a, b = st.columns(2)
    if a.button("Cancelar", use_container_width=True):
        for k in ("ci", "sug"): st.session_state.pop(k, None)
        st.rerun()
    if b.button("Ver apartamentos", type="primary", use_container_width=True):
        s = max(str(h), r["ini"]) if r else str(h)
        erros = [m for ok, m in [(len(nome.strip()) >= 3, "Informe o nome completo"), (cpf_ok(cpf), "CPF inválido"),
                 (len(re.sub(r"\D", "", zap)) in (10, 11), "WhatsApp com DDD é obrigatório"), (str(saida) > s, "Data de saída inválida")] if not ok]
        if erros: st.error(" · ".join(erros))
        else: st.session_state.sug = sugerir(int(hosp), cama, s, str(saida), ci or -1)
    if "sug" in st.session_state:
        sug = st.session_state.sug
        if not sug: st.warning("Nenhum apartamento livre em todo o período.")
        else:
            esc = st.radio("Apartamento (o primeiro é o sugerido)", sug, format_func=lambda a: f"Apto {a[0]} · {TIPOS[a[1]][2]} · até {a[2]}")
            if st.button("Confirmar check-in", type="primary", use_container_width=True):
                foto = reduz(f1 or f2) if (f1 or f2) else None
                p = dict(n=nome.strip(), c=mask_cpf(cpf), z=mask_zap(zap), h=int(hosp), f=str(saida), cm=cama, a=esc[0],
                         car=" · ".join(x for x in (mod, cor, placa.upper()) if x), ph=foto, cin=agora().strftime("%Y-%m-%dT%H:%M"))
                if r: ex("UPDATE reservas SET nome=:n,cpf=:c,zap=:z,hosp=:h,fim=:f,cama=:cm,apto=:a,carro=:car,foto=COALESCE(:ph,foto),cin=:cin WHERE id=:i", i=ci, **p)
                else: ex("INSERT INTO reservas(nome,cpf,zap,hosp,fim,cama,apto,carro,foto,cin,ini,origem) VALUES(:n,:c,:z,:h,:f,:cm,:a,:car,:ph,:cin,:hj,'Direto')", hj=str(h), **p)
                for k in ("ci", "sug"): st.session_state.pop(k, None)
                st.toast(f"Check-in feito: apto {esc[0]}"); st.rerun()

def tab_checkout(h):
    R = q(f"SELECT {COLS} FROM reservas WHERE cin IS NOT NULL AND chave IS NULL ORDER BY fim,nome")
    st.subheader("Hóspedes no prédio")
    if not R: st.caption("Ninguém no prédio.")
    for r in R:
        st.markdown(("🔴 " if r["fim"] < str(h) else "🟠 " if r["fim"] == str(h) else "") + f"**{r['nome']}**")
        linha(r, "Devolvida chave ?", f"co{r['id']}", lambda r: confirmar(r, h))

# ---------- administrador ----------
def detalhes(h):
    R = q(f"SELECT {COLS} FROM reservas ORDER BY ini DESC,nome")
    r = st.selectbox("Reserva", R, index=None, placeholder="Escolha uma reserva", format_func=lambda r: f"{r['nome']} · {br(r['ini'])}→{br(r['fim'])}")
    if not r: return
    z = re.sub(r"\D", "", r["zap"] or "")
    st.markdown(f"**Apto:** {r['apto'] or 'não alocado'}  \n**Hóspedes:** {r['hosp'] or 'a confirmar'}  \n**Datas:** {br(r['ini'])} → {br(r['fim'])}  \n**Origem:** {r['origem']}  \n"
                f"**CPF:** {'***.' + re.sub(r'\D', '', r['cpf'])[3:6] + '.***-**' if r['cpf'] else '—'}  \n"
                f"**WhatsApp:** {f'[{r['zap']}](https://wa.me/55{z})' if z else '—'}  \n**Automóvel:** {r['carro'] or '—'}")
    foto = q("SELECT foto FROM reservas WHERE id=:i", i=r["id"])[0]["foto"]
    if foto:
        with st.expander("Foto do documento"): st.image(bytes(foto))
    if r["cin"] and not r["chave"] and st.button("Devolvida chave ?", key="dchv"): confirmar(r, h)

def nova_reserva(h):
    with st.form("nova", clear_on_submit=True):
        nome = st.text_input("Nome"); hosp = st.number_input("Hóspedes", 1, 4, 2); org = st.selectbox("Origem", list(COR))
        ini = st.date_input("Entrada", h, format="DD/MM/YYYY"); fim = st.date_input("Saída", h + dt.timedelta(1), format="DD/MM/YYYY")
        cama = st.selectbox("Cama preferida", [""] + list(TIPOS), format_func=tlabel)
        apto = st.selectbox("Apartamento (opcional)", [""] + [a[0] for a in APTOS], format_func=lambda x: x or "Definir no check-in")
        if st.form_submit_button("Salvar", type="primary", use_container_width=True):
            if not nome.strip() or fim <= ini: st.error("Confira nome e datas")
            elif apto and conflito(apto, str(ini), str(fim)): st.error(f"Conflito de datas no apto {apto}")
            else:
                ex("INSERT INTO reservas(nome,hosp,origem,ini,fim,cama,apto) VALUES(:n,:h,:o,:i,:f,:c,:a)", n=nome.strip(), h=int(hosp), o=org, i=str(ini), f=str(fim), c=cama, a=apto)
                st.success("Reserva salva")

def parse_ics(t):
    t = re.sub(r"\r?\n[ \t]", "", t); ev = []
    for b in t.split("BEGIN:VEVENT")[1:]:
        g = lambda k: (re.search(rf"^{k}[^:\n]*:(.*)$", b, re.M) or [0, ""])[1].strip()
        d = lambda s: (m := re.search(r"(\d{4})(\d{2})(\d{2})", s)) and f"{m[1]}-{m[2]}-{m[3]}"
        ev.append(dict(uid=g("UID"), ini=d(g("DTSTART")), fim=d(g("DTEND")), sum=g("SUMMARY")))
    return [e for e in ev if e["uid"] and e["ini"] and e["fim"]]

def importar(h):
    org = st.selectbox("Origem", ["Airbnb", "Booking"]); ap = st.selectbox("Apartamento do anúncio", [""] + [a[0] for a in APTOS], format_func=lambda x: x or "Definir no check-in")
    arq = st.file_uploader("Arquivo .ics", type=["ics"]); txt = st.text_area("…ou cole o texto do calendário")
    ign = st.checkbox("Ignorar bloqueios (Not available / Closed)", value=org == "Booking", key=f"ign{org}")
    if st.button("Ver prévia"):
        ev = parse_ics(arq.getvalue().decode("utf-8", "ignore") if arq else txt)
        ex_ = {r["uid"]: r for r in q(f"SELECT {COLS} FROM reservas WHERE uid<>''")}; pv = dict(nv=[], al=[], sm=[], ig=[], rm=[], org=org); vistos = set()
        for e in ev:
            vistos.add(e["uid"])
            if e["fim"] <= str(h): pv["ig"].append({**e, "nt": "passado"}); continue
            if ign and re.search(r"not available|closed", e["sum"], re.I): pv["ig"].append({**e, "nt": "bloqueio"}); continue
            x = ex_.get(e["uid"])
            if x: pv["al" if (x["ini"], x["fim"]) != (e["ini"], e["fim"]) else "sm"].append({**e, "id": x["id"]})
            else:
                a = ap if ap and not conflito(ap, e["ini"], e["fim"]) else ""
                pv["nv"].append({**e, "apto": a, "nt": "conflito: sem apto" if ap and not a else ""})
        pv["rm"] = [r for r in ex_.values() if r["origem"] == org and not r["cin"] and r["fim"] > str(h) and r["uid"] not in vistos]
        st.session_state.pv = pv
    pv = st.session_state.get("pv")
    if pv:
        for k, t in (("nv", "Novas"), ("al", "Datas alteradas"), ("sm", "Sem mudança"), ("ig", "Ignoradas"), ("rm", "Removidas")):
            st.write(f"**{t} ({len(pv[k])})**")
            for e in pv[k] if k != "sm" else []: st.caption(f"{e.get('sum') or e.get('nome')} · {br(e['ini'])}→{br(e['fim'])} {e.get('nt', '')}")
        if st.button("Aplicar importação", type="primary"):
            for e in pv["nv"]: ex("INSERT INTO reservas(nome,hosp,origem,ini,fim,uid,apto) VALUES(:n,0,:o,:i,:f,:u,:a)", n=e["sum"] or pv["org"], o=pv["org"], i=e["ini"], f=e["fim"], u=e["uid"], a=e["apto"])
            for e in pv["al"]: ex("UPDATE reservas SET ini=:i,fim=:f WHERE id=:d", i=e["ini"], f=e["fim"], d=e["id"])
            for e in pv["rm"]: ex("DELETE FROM reservas WHERE id=:d", d=e["id"])
            del st.session_state["pv"]; st.success("Importação aplicada")

def tab_mapa(h):
    ms = st.session_state.setdefault("ms", h)
    a, b, c = st.columns(3)
    if a.button("‹ Semana", use_container_width=True): ms -= dt.timedelta(7)
    if b.button("Hoje", use_container_width=True): ms = h
    if c.button("Semana ›", use_container_width=True): ms += dt.timedelta(7)
    st.session_state.ms = ms; H = str(h)
    n = lambda sql: q(sql, h=H)[0]["n"]
    k = st.columns(2)
    k[0].metric("Ocupados hoje", n("SELECT COUNT(*) n FROM reservas WHERE cin IS NOT NULL AND chave IS NULL")); k[1].metric("Entradas hoje", n("SELECT COUNT(*) n FROM reservas WHERE ini=:h"))
    k[0].metric("Saídas hoje", n("SELECT COUNT(*) n FROM reservas WHERE fim=:h AND chave IS NULL")); k[1].metric("Sem apartamento", n("SELECT COUNT(*) n FROM reservas WHERE apto='' AND fim>=:h"))
    dias = [ms + dt.timedelta(i) for i in range(14)]; R = q(f"SELECT {COLS} FROM reservas WHERE apto<>'' AND ini<:f AND fim>:i", f=str(dias[-1] + dt.timedelta(1)), i=str(dias[0]))
    txt, sty = {}, {}
    for ap, _, _ in APTOS:
        for d in dias:
            r = next((r for r in R if r["apto"] == ap and r["ini"] <= str(d) < r["fim"]), None)
            txt[(ap, d)] = r["nome"].split()[0] if r else ""
            sty[(ap, d)] = f"background-color:{COR[r['origem']]}{'55' if r['chave'] else ''};color:#fff" if r else ("background-color:#ffe9a8" if d == h else "")
    cols = [d.strftime("%d/%m") for d in dias]; idx = [a[0] for a in APTOS]
    df = pd.DataFrame([[txt[(a, d)] for d in dias] for a in idx], index=idx, columns=cols)
    st_ = pd.DataFrame([[sty[(a, d)] for d in dias] for a in idx], index=idx, columns=cols)
    st.dataframe(df.style.apply(lambda _: st_, axis=None), height=620)
    st.caption("🟦 Booking · 🟪 Airbnb · 🟩 Direto · esmaecida = check-out feito")
    st.subheader("Aguardando alocação")
    for r in q(f"SELECT {COLS} FROM reservas WHERE apto='' AND fim>=:h ORDER BY ini", h=H): st.markdown(f"**{r['nome']}** · {r['origem']} · {r['hosp'] or '?'}p · {br(r['ini'])}→{br(r['fim'])}")
    with st.expander("Detalhes da reserva"): detalhes(h)
    with st.expander("Nova reserva"): nova_reserva(h)
    with st.expander("Importar iCal"): importar(h)

def tab_acessos():
    A = q("SELECT * FROM acessos ORDER BY email")
    st.subheader("Pedidos pendentes")
    for x in [a for a in A if a["status"] == "pendente"] or []:
        st.write(f"**{x['email']}** quer: {x['perfil']}"); a, b = st.columns(2)
        if a.button("Aprovar", key="ap" + x["email"], use_container_width=True): ex("UPDATE acessos SET status='aprovado' WHERE email=:e", e=x["email"]); st.rerun()
        if b.button("Negar", key="ng" + x["email"], use_container_width=True): ex("UPDATE acessos SET status='negado' WHERE email=:e", e=x["email"]); st.rerun()
    st.subheader("Com acesso")
    for x in [a for a in A if a["status"] == "aprovado"]:
        st.write(f"**{x['email']}** · {x['perfil']}")
        if st.button("Revogar", key="rv" + x["email"]): ex("UPDATE acessos SET status='negado' WHERE email=:e", e=x["email"]); st.rerun()
    st.download_button("Exportar para planilha (CSV)", pd.DataFrame(A).to_csv(index=False).encode("utf-8-sig"), "acessos.csv", "text/csv", use_container_width=True)

# ---------- principal ----------
init(); em = email(); h = agora().date()
admins = [a.lower() for a in st.secrets.get("admins", ["admin@local"])]
perfil = "admin" if em in admins else None
if not perfil:
    a = q("SELECT * FROM acessos WHERE email=:e", e=em); a = a[0] if a else None
    if a and a["status"] == "aprovado": perfil = a["perfil"]
    else:
        st.title("🏢 Reservas do Prédio")
        if a and a["status"] == "pendente": st.info("Aguardando aprovação do administrador.")
        else:
            if a: st.error("Acesso negado.")
            p = st.selectbox("Perfil desejado", ["porteiro", "admin"], format_func=lambda x: "Porteiro" if x == "porteiro" else "Administrador")
            if st.button("Solicitar acesso", type="primary"):
                ex("DELETE FROM acessos WHERE email=:e", e=em); ex("INSERT INTO acessos VALUES(:e,:p,'pendente')", e=em, p=p); st.rerun()
        st.stop()
nomes = ["Check-in", "Check-out"] + (["Mapa", "Acessos"] if perfil == "admin" else [])
for nm, t in zip(nomes, st.tabs(nomes)):
    with t: {"Check-in": lambda: tab_checkin(h), "Check-out": lambda: tab_checkout(h), "Mapa": lambda: tab_mapa(h), "Acessos": tab_acessos}[nm]()
