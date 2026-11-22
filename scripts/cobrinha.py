"""Gera a animação da cobrinha que come o gráfico de contribuições e cresce.

Uso: python scripts/cobrinha.py PASTA_DE_SAIDA
Precisa de GITHUB_TOKEN (no Actions, o token automático já serve).

Diferente do Platane/snk, a cobra anda só dentro das 7 linhas da grade e ganha um quadrado
de comprimento a cada dia com contribuição que come. O corpo é um traço grosso sobre o caminho
completo; a parte visível é controlada por stroke-dasharray/stroke-dashoffset animados em CSS.
"""
import json
import os
import sys
import urllib.request
from collections import deque
from pathlib import Path

USUARIO = os.environ.get("GITHUB_REPOSITORY_OWNER", "DevRGS")
CELULA, ESPACO, MARGEM = 11, 3, 6
PASSO_PX = CELULA + ESPACO

TEMAS = {
    "github-snake.svg": {
        "niveis": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
        "cobra": "#7c3aed", "olho": "#ffffff",
    },
    "github-snake-dark.svg": {
        "niveis": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
        "cobra": "#a78bfa", "olho": "#0d1117",
    },
}
NIVEL = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def buscar_grade() -> dict:
    consulta = """query($login: String!) { user(login: $login) { contributionsCollection {
      contributionCalendar { weeks { contributionDays { weekday contributionLevel } } } } } }"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": consulta, "variables": {"login": USUARIO}}).encode(),
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "User-Agent": "perfil-readme"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        dados = json.load(resp)
    if "errors" in dados:
        sys.exit(f"Erro na API do GitHub: {dados['errors']}")
    semanas = dados["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return {(x, d["weekday"]): NIVEL[d["contributionLevel"]]
            for x, semana in enumerate(semanas) for d in semana["contributionDays"]}


def caminho_mais_curto(grade: dict, inicio: tuple, alvos: set) -> list:
    """BFS dentro da grade até o alvo mais próximo. Devolve as casas percorridas (sem o início)."""
    anterior = {inicio: None}
    fila = deque([inicio])
    while fila:
        atual = fila.popleft()
        if atual in alvos:
            trajeto = []
            while atual != inicio:
                trajeto.append(atual)
                atual = anterior[atual]
            return trajeto[::-1]
        x, y = atual
        for viz in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if viz in grade and viz not in anterior:
                anterior[viz] = atual
                fila.append(viz)
    return []


def planejar(grade: dict):
    """Rota gulosa: sempre vai ao dia com contribuição mais próximo ainda não comido."""
    alvos = {c for c, n in grade.items() if n > 0}
    rota = [min(grade)]  # primeira casa existente da grade
    comidas = []  # (índice do passo, casa)
    if rota[0] in alvos:
        alvos.discard(rota[0])
        comidas.append((0, rota[0]))
    while alvos:
        trajeto = caminho_mais_curto(grade, rota[-1], alvos)
        if not trajeto:
            break
        rota += trajeto
        alvos.discard(trajeto[-1])
        comidas.append((len(rota) - 1, trajeto[-1]))
    return rota, comidas


def centro(casa: tuple) -> tuple:
    x, y = casa
    return MARGEM + x * PASSO_PX + CELULA / 2, MARGEM + y * PASSO_PX + CELULA / 2


def gerar_svg(grade: dict, rota: list, comidas: list, tema: dict) -> str:
    colunas = max(x for x, _ in grade) + 1
    largura = MARGEM * 2 + colunas * PASSO_PX - ESPACO
    altura = MARGEM * 2 + 7 * PASSO_PX - ESPACO
    passos = len(rota) - 1
    dur_passo = min(0.15, max(0.06, 50 / max(passos, 1)))
    pausa = 2.5
    total = passos * dur_passo + pausa
    pct = lambda t: f"{min(t / total * 100, 100):.4f}%"

    tempos_comida = [i * dur_passo for i, _ in comidas]

    def comprimento(t):  # cresce um quadrado ao longo do passo seguinte a cada comida (cauda para)
        return PASSO_PX * sum(min(max((t - tc) / dur_passo, 0), 1) for tc in tempos_comida)

    def cabeca(t):
        return min(t / dur_passo, passos) * PASSO_PX

    marcos = sorted({0.0, passos * dur_passo, total} | set(tempos_comida)
                    | {min(tc + dur_passo, passos * dur_passo) for tc in tempos_comida})
    grande = (passos + len(comidas) + 10) * PASSO_PX
    quadros_corpo = " ".join(
        f"{pct(t)}{{stroke-dasharray:{comprimento(t):.2f} {grande};stroke-dashoffset:{comprimento(t) - cabeca(t):.2f}}}"
        for t in marcos)

    # Cabeça (olhinho) acompanha a ponta do traço com translate em cada casa da rota.
    quadros_olho = " ".join(
        f"{pct(i * dur_passo)}{{transform:translate({centro(c)[0]:.1f}px,{centro(c)[1]:.1f}px)}}"
        for i, c in enumerate(rota))
    fim = centro(rota[-1])
    quadros_olho += f" 100%{{transform:translate({fim[0]:.1f}px,{fim[1]:.1f}px)}}"

    niveis = tema["niveis"]
    css = [
        f".c{{shape-rendering:geometricPrecision;rx:2;ry:2}}",
        f"#corpo{{fill:none;stroke:{tema['cobra']};stroke-width:{CELULA - 1};stroke-linecap:round;stroke-linejoin:round;"
        f"animation:corpo {total:.2f}s linear infinite}}",
        f"@keyframes corpo{{{quadros_corpo}}}",
        f"#olho{{fill:{tema['olho']};animation:olho {total:.2f}s linear infinite}}",
        f"@keyframes olho{{{quadros_olho}}}",
    ]
    comida_em = {casa: i * dur_passo for i, casa in comidas}
    rects = []
    for (x, y), nivel in sorted(grade.items()):
        px, py = MARGEM + x * PASSO_PX, MARGEM + y * PASSO_PX
        atributos = f'class="c" x="{px}" y="{py}" width="{CELULA}" height="{CELULA}" fill="{niveis[nivel]}"'
        if (x, y) in comida_em:
            nome = f"e{x}_{y}"
            t = comida_em[(x, y)]
            css.append(f"@keyframes {nome}{{0%,{pct(t)}{{fill:{niveis[nivel]}}}"
                       f"{pct(t + 0.001)},100%{{fill:{niveis[0]}}}}}")
            atributos += f' style="animation:{nome} {total:.2f}s linear infinite"'
        rects.append(f"<rect {atributos}/>")

    d = "M" + " L".join(f"{cx:.1f} {cy:.1f}" for cx, cy in map(centro, rota))
    if passos == 0:  # sem contribuições: cobra parada no canto
        css = css[:1]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {altura}" width="{largura}" height="{altura}">'
            f"<style>{''.join(css)}</style>{''.join(rects)}"
            f'<path id="corpo" d="{d}"/><circle id="olho" cx="0" cy="0" r="2"/></svg>')


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"Uso: python {sys.argv[0]} PASTA_DE_SAIDA")
    saida = Path(sys.argv[1])
    saida.mkdir(parents=True, exist_ok=True)
    grade = buscar_grade()
    rota, comidas = planejar(grade)
    for arquivo, tema in TEMAS.items():
        (saida / arquivo).write_text(gerar_svg(grade, rota, comidas, tema), encoding="utf-8")
    print(f"{len(comidas)} dias comidos em {len(rota) - 1} passos.")


if __name__ == "__main__":
    main()
