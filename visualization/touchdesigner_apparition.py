"""Horloge de la transition du portrait dans /trait_impulsif/apparition."""

# Le module est recréé à l’ouverture du .toe. L’horloge repart ainsi avec le projet.
_depart = None


def temps(maintenant):
    global _depart
    if _depart is None:
        _depart = maintenant
    t = max(0.0, maintenant - _depart)
    if parent().par.Boucle.eval():
        periode = max(op("mapping").module.valeur("periode"), 0.1)
        t %= periode
    return t


def rejouer():
    global _depart
    _depart = absTime.seconds
    parametre = parent().par.Departapparition
    parametre.readOnly = False
    parametre.val = _depart
    parametre.readOnly = True
