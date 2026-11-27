"""
Etapa 07, parte 2: contagem de termos no texto completo dos includes (dicionários de expressões regulares, sem LLM).

O texto vem de data/fulltext/text/ e data/rounds/fulltext/text/ (o extrator já corta as referências). Cada
categoria é um padrão; um artigo "menciona" a categoria se o padrão aparece pelo menos MIN_HITS vezes. Isso mede
presença no texto, não a resposta à QP: o que responde à QP é a marcação humana do artefato.

  uv run --extra analysis python scripts/final/mineracao.py

Grava results/final/dados/mencoes_<grupo>.csv (contagem por artigo) e mencoes_resumo.csv.
"""
import json
import os
import re
from pathlib import Path

import pandas as pd

DADOS = Path("results/final/dados")
MIN_HITS = 2

# robô: (padrão, morfologia)
ROBOS = {
    "NAO": (r"\bNAO(?:\s?V?\d)?\b|\bNao\b", "humanoide"),
    "MEDi": (r"\bMEDi|\bMEDI\b", "humanoide"),
    "Arash": (r"\bArash\b", "humanoide"),
    "Poppy": (r"\bPoppy\b", "humanoide"),
    "Pepper": (r"\bPepper\b", "humanoide"),
    "Zora": (r"\bZora\b", "humanoide"),
    "Kaspar": (r"\bKASPAR\b|\bKaspar\b", "humanoide"),
    "QTrobot": (r"\bQT ?robot\b|\bQTrobot\b", "humanoide"),
    "iCub": (r"\biCub\b", "humanoide"),
    "Robovie": (r"\bRobovie\b", "humanoide"),
    "Sota": (r"\bSota\b", "humanoide"),
    "Ryan": (r"\bRyan\b(?= robot| companion|,? the)", "humanoide"),
    "Nadine": (r"\bNadine\b", "humanoide"),
    "Sophia": (r"\bSophia\b(?= robot|,? the robot)", "humanoide"),
    "Telenoid": (r"\bTelenoid\b", "humanoide"),
    "Alpha": (r"\bAlpha ?(?:1|2|Mini)\b", "humanoide"),
    "Furhat": (r"\bFurhat\b", "cabeça/rosto"),
    "Buddy": (r"\bBUDDY\b|\bBuddy\b(?= robot)", "outro"),
    "PARO": (r"\bPARO\b|\bParo\b", "zoomórfico"),
    "Huggable": (r"\bHuggable\b", "zoomórfico"),
    "AIBO": (r"\bAIBO\b|\baibo\b|\bAibo\b", "zoomórfico"),
    "Pleo": (r"\bPleo\b|\bPLEO\b", "zoomórfico"),
    "JustoCat": (r"\bJustoCat\b", "zoomórfico"),
    "Probo": (r"\bProbo\b", "zoomórfico"),
    "MiRo": (r"\bMiRo\b", "zoomórfico"),
    "Joy for All": (r"\bJoy for All\b", "zoomórfico"),
    "iCat": (r"\biCat\b", "zoomórfico"),
    "Keepon": (r"\bKeepon\b", "zoomórfico"),
    "Tega": (r"\bTega\b", "zoomórfico"),
    "Dragonbot": (r"\bDragon[Bb]ot\b", "zoomórfico"),
    "Jibo": (r"\bJibo\b", "outro"),
    "ElliQ": (r"\bElliQ\b", "outro"),
    "Mabu": (r"\bMabu\b", "outro"),
    "Misty": (r"\bMisty\b", "outro"),
    "Temi": (r"\btemi\b|\bTemi\b|\bTEMI\b", "outro"),
    "STRANDS": (r"\bSTRANDS\b", "outro"),
    "Care-O-bot": (r"\bCare-O-bot\b", "outro"),
    "Kompaï": (r"\bKompa[iï]\b", "outro"),
    "Hobbit": (r"\bHobbit\b", "outro"),
    "Stevie": (r"\bStevie\b", "outro"),
    "Cozmo/Vector": (r"\bCozmo\b|\bVector\b(?= robot)", "outro"),
    "Lio": (r"\bLio\b", "outro"),
    "TIAGo": (r"\bTIAGo\b", "outro"),
    "Moxie": (r"\bMoxie\b", "outro"),
    "Bandit": (r"\bBandit\b", "outro"),
    "RAMCIP": (r"\bRAMCIP\b", "outro"),
    "Mario (MARIO)": (r"\bMARIO\b", "outro"),
    # robôs próprios ou pouco conhecidos achados nos artigos sem robô identificado (26/11/2026); morfologia só
    # quando o próprio texto a descreve, senão "próprio (não classificado)"
    "Robin": (r"\bRobin\b", "humanoide"),
    "Alter-Ego": (r"\bAlter-?Ego\b", "humanoide"),
    "R1 (IIT)": (r"\bR1 humanoid\b|\bR1 robot\b|\bthe R1\b", "humanoide"),
    "Flo / Lil'Flo": (r"\bLil.?Flo\b|\bFlo\b", "humanoide"),
    "MotionBuddy": (r"\bMotionBuddy\b", "humanoide"),
    "MAKI (IVEY)": (r"\bIVEY\b|\bMAKI\b", "cabeça/rosto"),
    "LOVOT": (r"\bLOVOT\b|\bLovot\b", "zoomórfico"),
    "Cocoron": (r"\bCocoron\b", "zoomórfico"),
    "Silver (gato robô)": (r"\bSilver Cat\b|\b“?Silver”?(?= was| cat| robot)", "zoomórfico"),
    "Pioneer 2DX": (r"\bPioneer\b", "outro"),
    "Edù": (r"\bEdù\b", "próprio (não classificado)"),
    "Mirrly": (r"\bMirrly\b", "próprio (não classificado)"),
    "Pukkabot": (r"\bPukkabot\b", "próprio (não classificado)"),
    "URSUS": (r"\bURSUS\b|\bUrsus\b", "próprio (não classificado)"),
}

# artigos sem robô principal: nenhum nome do dicionário, ou só citações de passagem (1 ou 2 menções)
SEM_ROBO = ("nenhum robô nomeado", "robô citado de passagem")

GRUPOS = {
    "contexto": {
        "Hospital": r"\bhospital(?:s|ized|isation|ization)?\b|\bward\b",
        "UTI / emergência": r"\bintensive care\b|\bICU\b|\bemergency (?:department|room)\b",
        "Pediatria / oncologia infantil": r"\bpaediatric|\bpediatric|\bchildren'?s hospital\b",
        "Clínica / ambulatório": r"\bclinic(?:s)?\b|\boutpatient|\bconsultation room\b|\bdental\b",
        "Centro de reabilitação": r"\brehabilitation (?:cent(?:er|re)|unit|clinic|hospital|ward)\b",
        "Casa de repouso / ILPI": r"\bnursing home|\bcare home|\blong-term care\b|\bresidential care|\bassisted living\b|\bcare facilit",
        "Domicílio": r"\bin-home\b|\bat home\b|\bin (?:their|the participants'?) homes?\b|\bhome environment\b|\bhome setting",
        "Centro-dia": r"\bday[- ]care cent|\badult day\b|\bday cent(?:er|re)\b",
        "Laboratório": r"\blab(?:oratory)?[- ](?:setting|study|studies|experiment|environment|conditions|based)\b|\bliving lab\b|\bin (?:the|a|our) lab(?:oratory)?\b",
        "Escola": r"\bschool(?:s)?\b(?! of)|\bclassroom",
    },
    "populacao": {
        "Crianças": r"\bchild(?:ren)?\b|\bkids?\b|\bpaediatric|\bpediatric",
        "Adolescentes / jovens": r"\badolescen|\bteen|\byoung adults?\b",
        "Idosos": r"\bolder adults?\b|\belderly\b|\bseniors?\b|\bolder people\b|\bolder persons?\b|\baged care\b",
        "Demência / Alzheimer": r"\bdementia\b|\bAlzheimer",
        "Comprometimento cognitivo leve": r"\bmild cognitive impairment\b|\bMCI\b",
        "AVC": r"\bstroke\b|\bpost-stroke\b",
        "Autismo (TEA)": r"\bautis|\bASD\b",
        "Câncer": r"\bcancer\b|\boncolog",
        "Cardiopatias": r"\bcardiac\b|\bheart failure\b|\bcardiovascular\b",
        "Paralisia cerebral / deficiência motora": r"\bcerebral palsy\b|\bmotor impairment",
        "Parkinson": r"\bParkinson",
        "Depressão / saúde mental": r"\bdepress(?:ion|ive)\b|\bmental health\b|\bschizophren|\bpsychiatric",
        "Diabetes": r"\bdiabet",
        "Profissionais de saúde": r"\bnurs(?:e|es|ing staff)\b|\bclinicians?\b|\bhealthcare (?:professionals|workers|staff)\b|\bphysicians?\b|\btherapists?\b|\bstaff members?\b",
        "Cuidadores / familiares": r"\bcaregivers?\b|\bcarers?\b|\bfamily members?\b|\bparents\b",
        "Estudantes / adultos saudáveis": r"\b(?:university |college )?students\b|\bhealthy adults?\b|\bhealthy volunteers\b",
    },
    "qp1_fisico": {
        "Aparência (geral)": r"\bappearance\b|\blook(?:s)? like\b",
        "Antropomorfismo": r"\banthropomorph|\bhuman-?like\b|\bhumanlike\b",
        "Humanoide": r"\bhumanoid\b",
        "Zoomorfismo / animal": r"\bzoomorph|\banimal-?like\b|\bpet-?like\b|\bpet robot\b|\bseal\b|\bdog\b|\bcat\b",
        "Tamanho / altura": r"\bsize\b|\bheight\b|\btall\b|\bsmall(?:er)? robot\b|\bcm\b",
        "Rosto / face": r"\bface\b|\bfacial features\b|\bfaces\b",
        "Olhos": r"\beyes?\b",
        "Cabeça": r"\bhead\b",
        "Braços / mãos": r"\barms?\b|\bhands?\b",
        "Cor": r"\bcolou?rs?\b|\bcolou?red\b",
        "Material / textura / maciez": r"\bmaterials?\b|\btextur|\bsoft\b|\bfur\b|\bfurry\b|\bplush\b|\bskin\b",
        "Forma / morfologia": r"\bshape\b|\bmorpholog|\bembodiment\b|\bembodied\b",
        "Tela / display": r"\bscreen\b|\bdisplay\b|\btablet\b",
        "Peso": r"\bweight\b|\bkg\b",
        "Fofura / aparência infantil": r"\bcute(?:ness)?\b|\bbaby-?like\b|\btoy-?like\b",
        "Uncanny valley": r"\buncanny\b",
    },
    "qp2_comunicacao": {
        "Fala / voz": r"\bspeech\b|\bspeak(?:s|ing)?\b|\bvoice\b|\bverbal\b|\bspoken\b",
        "Diálogo / conversa": r"\bdialog(?:ue)?s?\b|\bconversation",
        "Gestos": r"\bgestur",
        "Olhar / contato visual": r"\bgaze\b|\beye contact\b",
        "Expressão facial": r"\bfacial expression",
        "Toque / háptico": r"\btouch(?:ing|ed|es)?\b|\bhaptic|\btactile",
        "Movimento / postura": r"\bmovements?\b|\bbody language\b|\bposture|\bmotion\b",
        "Luzes / LEDs": r"\bLEDs?\b|\blights?\b",
        "Som / música": r"\bsounds?\b|\bmusic\b|\bsing(?:ing|s)?\b|\bsong",
        "Tela / tablet (interface)": r"\btablet\b|\btouch ?screen\b|\bGUI\b|\binterface\b",
        "Não verbal (geral)": r"\bnon-?verbal\b",
        "Multimodal": r"\bmultimodal|\bmulti-modal",
        "Proxêmica / distância": r"\bproxemic|\binterpersonal distance\b|\bpersonal space\b",
        "Reconhecimento de fala": r"\bspeech recognition\b|\bASR\b|\bvoice recognition\b",
        "LLM / IA generativa": r"\bLLMs?\b|\blarge language model|\bChatGPT\b|\bGPT-?\d",
        "Wizard of Oz": r"\bWizard[- ]of[- ]Oz\b|\bWoZ\b|\bteleoperat",
    },
    "qp3_emocao": {
        "Emoção (geral)": r"\bemotion(?:s|al)?\b",
        "Empatia": r"\bempath",
        "Personalidade": r"\bpersonalit",
        "Afeto": r"\baffect(?:ive)?\b",
        "Alegria / felicidade": r"\bhapp(?:y|iness)\b|\bjoy\b",
        "Tristeza": r"\bsad(?:ness)?\b",
        "Raiva": r"\banger\b|\bangry\b",
        "Medo": r"\bfear\b|\bscared\b|\bafraid\b",
        "Surpresa": r"\bsurpris",
        "Humor / piada": r"\bhumou?r\b|\bjokes?\b|\bfunny\b",
        "Expressividade": r"\bexpressiv",
        "Introversão / extroversão": r"\bextrover|\bintrover|\bextravert",
        "Reconhecimento de emoção": r"\bemotion recognition\b|\baffect recognition\b|\brecogni[sz]e emotions?\b",
        "Vínculo / apego / companhia": r"\battachment\b|\bbond(?:ing)?\b|\bcompanion(?:ship)?\b",
        "Engano / ética da emoção": r"\bdecepti|\bdeceiv",
    },
    "qp4_avaliacao": {
        "Questionário (geral)": r"\bquestionnaires?\b|\bsurveys?\b",
        "Escala Likert": r"\bLikert\b",
        "Entrevista": r"\binterview",
        "Grupo focal": r"\bfocus groups?\b",
        "Observação / vídeo": r"\bobservation(?:s|al)?\b|\bvideo[- ]?(?:record|coded|coding|analysis)",
        "Análise temática": r"\bthematic analysis\b",
        "Godspeed": r"\bGodspeed\b",
        "SUS (usabilidade)": r"\bSystem Usability Scale\b|\bSUS\b",
        "Almere": r"\bAlmere\b",
        "UTAUT": r"\bUTAUT",
        "TAM": r"\bTechnology Acceptance Model\b|\bTAM\b",
        "NARS (atitudes negativas)": r"\bNARS\b|\bNegative Attitudes? (?:towards|toward) Robots? Scale\b",
        "RAS (ansiedade com robôs)": r"\bRobot Anxiety Scale\b|\bRAS\b",
        "PANAS": r"\bPANAS\b",
        "STAI / ansiedade": r"\bSTAI\b|\bState-Trait Anxiety\b",
        "Escalas de solidão (UCLA)": r"\bUCLA Loneliness\b|\bloneliness scale\b",
        "Depressão (GDS etc.)": r"\bGDS\b|\bGeriatric Depression\b|\bCES-D\b|\bPHQ",
        "Qualidade de vida": r"\bquality of life\b|\bQoL\b|\bQUALID\b",
        "Agitação / NPI / CMAI": r"\bCMAI\b|\bNPI\b|\bagitation\b",
        "MMSE / cognição": r"\bMMSE\b|\bMoCA\b|\bMini-Mental\b",
        "Dor (escalas)": r"\bpain (?:scale|score)|\bFLACC\b|\bFaces Pain\b|\bVAS\b",
        "Fisiológico": r"\bheart rate\b|\bskin conductance\b|\belectrodermal\b|\bEDA\b|\bcortisol\b|\bEEG\b|\bblood pressure\b|\bphysiological",
        "Engajamento": r"\bengagement\b",
        "Métricas de tarefa / desempenho": r"\btask completion\b|\bcompletion time\b|\berror rate\b|\bperformance\b",
        "Logs do sistema": r"\blogs?\b|\blogged\b",
    },
    "desenho_estudo": {
        "Ensaio randomizado (RCT)": r"\brandomi[sz]ed\b|\bRCT\b",
        "Controlado / grupo controle": r"\bcontrol group\b|\bcontrolled (?:trial|study)\b",
        "Piloto / viabilidade": r"\bpilot\b|\bfeasibility\b",
        "Estudo de caso": r"\bcase stud(?:y|ies)\b",
        "Longitudinal / longo prazo": r"\blongitudinal\b|\blong-term\b|\bweeks?\b",
        "Métodos mistos": r"\bmixed[- ]methods?\b",
        "Qualitativo": r"\bqualitative\b",
        "Quantitativo": r"\bquantitative\b",
        "Entre sujeitos": r"\bbetween[- ]subjects?\b",
        "Intra sujeitos": r"\bwithin[- ]subjects?\b",
        "Participativo / co-design": r"\bco-?design|\bparticipatory design\b|\buser-centred|\buser-centered",
        "Experimento em campo": r"\bfield (?:study|trial|experiment|test)\b|\bin the wild\b",
    },
}

N_PATTERN = re.compile(
    r"\b(?:N|n)\s*=\s*(\d{1,4})\b|\b(\d{1,4})\s+(?:participants|patients|children|older adults|residents|subjects|"
    r"users|caregivers|nurses|people|elderly|individuals|persons|adults|staff members|volunteers|families)\b")
NUM_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30}


class Texto:
    @classmethod
    def load(cls, key: str) -> list[dict]:
        path = f"data/fulltext/text/{key}.jsonl"
        if not os.path.exists(path):
            path = f"data/rounds/fulltext/text/{key}.jsonl"
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    AFILIACAO = re.compile(r"@|\bDepartment of\b|\bSchool of\b|\bFaculty of\b|\bUniversity Hospital\b|"
                           r"\bCorresponding author|\bAffiliations?\b|\bInstitute of\b|\bLaborator(?:y|ies) (?:of|for)\b")

    @classmethod
    def body(cls, paras: list[dict]) -> list[dict]:
        """Sem a folha de rosto (seção vazia ou 'Title page') e sem parágrafos curtos de afiliação."""
        kept = []
        for p in paras:
            section = (p.get("section") or "").strip().lower()
            if section in ("", "title page"):
                continue
            if len(p["text"]) < 400 and cls.AFILIACAO.search(p["text"]):
                continue
            kept.append(p)
        return kept or paras

    @classmethod
    def full(cls, paras: list[dict]) -> str:
        return "\n".join(p["text"] for p in cls.body(paras))


class Amostra:
    """N de participantes: primeiro 'N = x' ou 'x participants' nas seções de método; senão, no texto todo."""

    METHOD = re.compile(r"method|participant|subject|sample|recruit|procedure|study design|materials", re.I)

    @classmethod
    def find(cls, paras: list[dict]) -> tuple[int | None, str]:
        ordered = [p for p in paras if cls.METHOD.search(p.get("section") or "")] + paras
        for p in ordered:
            for m in N_PATTERN.finditer(p["text"]):
                n = int(m.group(1) or m.group(2))
                if 1 < n < 5000 and not re.search(r"(?:19|20)\d\d", m.group(0)):
                    start = max(0, m.start() - 80)
                    return n, p["text"][start : m.end() + 40].replace("\n", " ")
        return None, ""


def main():
    inc = pd.read_csv(DADOS / "includes.csv")
    resumo, robos_rows, n_rows = [], [], []
    tables = {g: [] for g in GRUPOS}
    for key in inc.key:
        paras = Texto.load(key)
        text = Texto.full(paras)
        for grupo, cats in GRUPOS.items():
            row = {"key": key}
            for cat, pat in cats.items():
                row[cat] = len(re.findall(pat, text, flags=re.I if grupo != "qp4_avaliacao" else 0))
            tables[grupo].append(row)
        row = {"key": key}
        for robo, (pat, _) in ROBOS.items():
            row[robo] = len(re.findall(pat, text))
        robos_rows.append(row)
        n, snippet = Amostra.find(paras)
        n_rows.append({"key": key, "n_participantes_auto": n, "trecho_n": snippet, "palavras": len(text.split())})

    for grupo, rows in tables.items():
        df = pd.DataFrame(rows)
        df.to_csv(DADOS / f"mencoes_{grupo}.csv", index=False)
        for cat in GRUPOS[grupo]:
            resumo.append({"grupo": grupo, "categoria": cat, "artigos": int((df[cat] >= MIN_HITS).sum()),
                           "mencoes_total": int(df[cat].sum())})

    rob = pd.DataFrame(robos_rows)
    rob.to_csv(DADOS / "mencoes_robos.csv", index=False)
    principal = []
    for _, r in rob.iterrows():
        counts = r.drop("key").astype(int)
        top = counts.idxmax()
        if counts[top] >= 3:
            principal.append({"key": r.key, "robo_principal": top, "morfologia": ROBOS[top][1], "mencoes": int(counts[top])})
        else:
            label = SEM_ROBO[1] if counts[top] > 0 else SEM_ROBO[0]
            principal.append({"key": r.key, "robo_principal": label, "morfologia": label, "mencoes": int(counts[top])})
    pd.DataFrame(principal).to_csv(DADOS / "robo_principal.csv", index=False)
    for robo in ROBOS:
        resumo.append({"grupo": "robos", "categoria": robo, "artigos": int((rob[robo] >= MIN_HITS).sum()),
                       "mencoes_total": int(rob[robo].sum())})

    dominante = []
    for grupo in ("contexto", "populacao"):
        df = pd.DataFrame(tables[grupo]).set_index("key")
        for key, r in df.iterrows():
            top = r.idxmax()
            dominante.append({"key": key, "grupo": grupo, "dominante": top if r[top] >= 3 else "não identificado",
                              "mencoes": int(r[top])})
    pd.DataFrame(dominante).to_csv(DADOS / "dominante_contexto_populacao.csv", index=False)
    pd.DataFrame(n_rows).to_csv(DADOS / "amostra_auto.csv", index=False)
    pd.DataFrame(resumo).to_csv(DADOS / "mencoes_resumo.csv", index=False)
    print(pd.DataFrame(principal).robo_principal.value_counts().head(15).to_string())
    print(pd.DataFrame(n_rows).n_participantes_auto.describe().to_string())


if __name__ == "__main__":
    main()
