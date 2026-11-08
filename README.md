# Reservas do Prédio (Streamlit)

App de reservas, check-in/check-out e mapa de ocupação. Perfis: Porteiro e Administrador. Login Google, banco SQL.

## Rodar local
    pip install -r requirements.txt
    streamlit run app.py        # usa SQLite (reservas.db) e e-mail "admin@local"
    python seed.py              # opcional: 20 reservas de teste (rode depois de abrir o app uma vez)

## Publicar (GitHub + Streamlit Community Cloud)
1. Crie um repositório **privado** no GitHub e envie estes arquivos (o `.gitignore` já protege segredos e o banco local).
2. Crie um banco Postgres gratuito (ex.: Supabase) e copie a URL de conexão. **Não use SQLite na nuvem**: o disco é apagado a cada reinício.
3. Em Google Cloud Console, crie um cliente OAuth ("Aplicativo da Web") com URI de redirecionamento `https://SEU-APP.streamlit.app/oauth2callback`.
4. Em share.streamlit.io: New app → escolha o repositório → `app.py`. Em Settings → Secrets cole o conteúdo de `.streamlit/secrets.toml.example` já preenchido.
5. Para carregar os dados de teste na nuvem: `DB_URL="postgresql+psycopg2://..." python seed.py`.

## Perfis
- E-mails em `admins` (secrets) são administradores. Os demais pedem acesso e o administrador aprova na aba Acessos.
