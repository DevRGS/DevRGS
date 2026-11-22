"""Atualiza as seções dinâmicas do README do perfil.

Uso (chamado pelos workflows em .github/workflows):
  python scripts/perfil.py recentes   -> lista de repositórios mexidos recentemente
  python scripts/perfil.py issue      -> processa uma jogada do jogo da velha

Sem dependências externas. Os dados da issue chegam por variáveis de ambiente
(ISSUE_TITLE, ISSUE_USER), nunca interpolados no shell.
A resposta para a pessoa é escrita em resposta.md, que o workflow comenta na issue.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
README = RAIZ / "README.md"
ESTADO = RAIZ / "dados"
USUARIO = "DevRGS"
REPO = os.environ.get("GITHUB_REPOSITORY", f"{USUARIO}/{USUARIO}")
VAZIO = " "
LINHAS = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def trocar_secao(nome: str, conteudo: str) -> None:
    texto = README.read_text(encoding="utf-8")
    padrao = re.compile(rf"(<!-- {nome}:inicio -->\n).*?(\n<!-- {nome}:fim -->)", re.S)
    if not padrao.search(texto):
        sys.exit(f"Marcadores da seção '{nome}' não encontrados no README.")
    README.write_text(padrao.sub(lambda m: m.group(1) + conteudo + m.group(2), texto), encoding="utf-8")


def ler_json(nome: str, padrao):
    arquivo = ESTADO / nome
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else padrao


def salvar_json(nome: str, dados) -> None:
    ESTADO.mkdir(exist_ok=True)
    (ESTADO / nome).write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def limpar(texto: str, limite: int) -> str:
    """Deixa texto de visitante seguro para entrar no Markdown."""
    texto = re.sub(r"<[^>]*>", " ", texto or "")
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = re.sub(r"[<>\[\]()|`*_~#!\\]", "", texto)
    texto = re.sub(r"https?:\S+", "", texto).strip()
    return texto[:limite]


def responder(mensagem: str) -> None:
    (RAIZ / "resposta.md").write_text(mensagem, encoding="utf-8")


# ---------- Repositórios recentes (dica 9) ----------

def recentes() -> None:
    req = urllib.request.Request(
        f"https://api.github.com/users/{USUARIO}/repos?sort=pushed&per_page=30",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "perfil-readme"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        repos = json.load(resp)

    linhas = []
    for r in repos:
        if r["fork"] or r["name"] == USUARIO:
            continue
        data = datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")).strftime("%d/%m/%Y")
        desc = limpar(r["description"] or "", 90)
        extra = f" · [abrir]({r['homepage']})" if r.get("homepage") else ""
        linhas.append(f"- [**{r['name']}**]({r['html_url']}){' · ' + desc if desc else ''}{extra} · _{data}_")
        if len(linhas) == 5:
            break
    agora = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    trocar_secao("recentes", "\n".join(linhas) + f"\n\n<sub>Atualizado automaticamente em {agora}.</sub>")


# ---------- Jogo da velha (dicas 5 e 6) ----------

def novo_jogo() -> dict:
    return {"tabuleiro": [VAZIO] * 9, "vez": "X", "jogadas": [], "placar": {"X": 0, "O": 0, "velha": 0}}


def vencedor(t: list) -> str | None:
    for a, b, c in LINHAS:
        if t[a] != VAZIO and t[a] == t[b] == t[c]:
            return t[a]
    return "velha" if VAZIO not in t else None


def link_issue(titulo: str, corpo: str) -> str:
    from urllib.parse import quote
    return f"https://github.com/{REPO}/issues/new?title={quote(titulo)}&body={quote(corpo)}"


def desenhar_velha(jogo: dict) -> str:
    t = jogo["tabuleiro"]
    simbolo = {"X": "❌", "O": "⭕"}
    fim = vencedor(t)
    celulas = []
    for i, valor in enumerate(t):
        if valor != VAZIO:
            celulas.append(simbolo[valor])
        elif fim:
            celulas.append("⬜")
        else:
            corpo = "Só clicar em Submit new issue. O GitHub Actions faz o resto!"
            celulas.append(f"[⬜]({link_issue(f'velha|jogar|{i}', corpo)})")
    tabela = ["| | | |", "|:-:|:-:|:-:|"]
    for linha in range(3):
        tabela.append("| " + " | ".join(celulas[linha * 3:linha * 3 + 3]) + " |")

    if fim == "velha":
        status = "**Deu velha!** 🤝"
    elif fim:
        status = f"**{simbolo[fim]} venceu!** 🎉"
    else:
        status = f"É a vez do {simbolo[jogo['vez']]}"
    if fim:
        status += f" [**Começar outra partida**]({link_issue('velha|novo', 'Só clicar em Submit new issue.')})"

    p = jogo["placar"]
    partes = [status, "", *tabela, "",
              f"Placar geral: ❌ {p['X']} · ⭕ {p['O']} · 🤝 {p['velha']}"]
    if jogo["jogadas"]:
        ultimas = jogo["jogadas"][-5:][::-1]
        partes += ["", "Últimas jogadas: " + " · ".join(
            f"{simbolo[j['peca']]} [@{j['usuario']}](https://github.com/{j['usuario']})" for j in ultimas)]
    return "\n".join(partes)


def jogar_velha(acao: str, usuario: str) -> None:
    jogo = ler_json("velha.json", novo_jogo())
    t = jogo["tabuleiro"]
    if acao == "novo":
        if not vencedor(t):
            return responder("A partida atual ainda não acabou. Escolha uma casa vazia no README!")
        placar = jogo["placar"]
        jogo = novo_jogo()
        jogo["placar"] = placar
        mensagem = "Nova partida criada. Você pode fazer a primeira jogada!"
    else:
        m = re.fullmatch(r"jogar\|([0-8])", acao)
        if not m:
            return responder("Não entendi essa jogada. Use os links do tabuleiro no README.")
        casa = int(m.group(1))
        if vencedor(t):
            return responder("Essa partida já terminou. Use o link para começar outra.")
        if t[casa] != VAZIO:
            return responder("Alguém jogou nessa casa antes de você. Tente outra!")
        peca = jogo["vez"]
        t[casa] = peca
        jogo["jogadas"].append({"usuario": usuario, "peca": peca, "casa": casa})
        jogo["vez"] = "O" if peca == "X" else "X"
        fim = vencedor(t)
        if fim:
            jogo["placar"][fim] += 1
        mensagem = "Jogada registrada! Valeu por jogar. 🎮" + (" E essa partida acabou!" if fim else "")
    salvar_json("velha.json", jogo)
    trocar_secao("velha", desenhar_velha(jogo))
    responder(mensagem + f"\n\nVeja o tabuleiro: https://github.com/{USUARIO}")


def issue() -> None:
    titulo = (os.environ.get("ISSUE_TITLE") or "").strip()
    usuario = re.sub(r"[^A-Za-z0-9-]", "", os.environ.get("ISSUE_USER") or "")[:39]
    if titulo.startswith("velha|"):
        jogar_velha(titulo[len("velha|"):], usuario)


def iniciar() -> None:
    """Desenha o tabuleiro vazio e a lista de recentes na primeira execução."""
    trocar_secao("velha", desenhar_velha(ler_json("velha.json", novo_jogo())))
    recentes()


if __name__ == "__main__":
    comandos = {"recentes": recentes, "issue": issue, "iniciar": iniciar}
    if len(sys.argv) != 2 or sys.argv[1] not in comandos:
        sys.exit(f"Uso: python {sys.argv[0]} [{'|'.join(comandos)}]")
    comandos[sys.argv[1]]()
