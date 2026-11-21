"""Callback du Text DAT /osc/osc_in_callbacks dans le portrait MindSight."""

from math import isfinite

TRAITS = (
    "enthousiasme", "reveur", "creativite", "analytique", "torture",
    "bienveillance", "autocritique", "humour", "confiance_en_soi",
    "extraversion", "impulsif",
)
ALIASES = {"torture": "angoisse", "impulsif": "impulsivite"}


def _borne(valeur, maximum):
    if type(valeur) is float and isfinite(valeur):
        return max(0.0, min(maximum, valeur))
    return None


def _cible(chemin, nom):
    comp = op(chemin)
    param = getattr(comp.par, nom, None) if comp is not None else None
    while getattr(param, "mode", None) == ParMode.BIND:
        param = param.bindMaster
    if getattr(param, "mode", None) == ParMode.CONSTANT:
        return param
    print(f"OSC — vérifier la cible ou le maître de {chemin}.{nom}")
    return None


def _profil(table, args):
    if len(args) != len(TRAITS):
        return
    valeurs = [_borne(valeur, 10.0) for valeur in args]
    if None in valeurs:
        return
    cibles = [_cible(f"/trait_{nom}", "Intensite") for nom in TRAITS]
    if any(cible is None for cible in cibles):
        return
    for nom, cible, valeur in zip(TRAITS, cibles, valeurs):
        cible.val = valeur
        table[ALIASES.get(nom, nom), "intensite"] = valeur


def _dimension(table, nom, valeur):
    nom = ALIASES.get(nom, nom)
    chemin = table[nom, "composant"]
    valeur = _borne(valeur, 10.0)
    if chemin is None or valeur is None:
        return
    if chemin.val:
        cible = _cible(chemin.val, "Intensite")
        if cible is not None:
            cible.val = valeur
    table[nom, "intensite"] = valeur


def onReceiveOSC(dat, rowIndex, message, byteData, timeStamp, address, args, peer):
    if address == "/profil":
        _profil(dat.parent().op("dimensions"), args)
    elif len(args) == 1:
        valeur = args[0]
        if address == "/trait/impulsif/rejouer" and type(valeur) is int and valeur == 1:
            op("/trait_impulsif/apparition").module.rejouer()
        elif address == "/trait/impulsif/boucle" and type(valeur) is int and valeur in (0, 1):
            cible = _cible("/trait_impulsif", "Boucle")
            if cible is not None:
                cible.val = bool(valeur)
        elif address == "/finition/force":
            force = _borne(valeur, 1.0)
            if force is not None:
                cible = _cible("/finition", "Force")
                if cible is not None:
                    cible.val = force
        elif address.startswith("/trait/"):
            _dimension(dat.parent().op("dimensions"), address.removeprefix("/trait/"), valeur)
