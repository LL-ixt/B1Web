"""Shared dimensions, OSM ids and build switches for the B1 model."""

B1_WAY = '184021007'
ENTRANCE_PART = '1207082389'

GROUND_H = 4.5      # ground floor storey height (m)
FLOOR_H = 3.6       # typical storey height (m)
PARAPET = 1.0
BAND_D = 0.35       # projection of the horizontal spandrel bands
PIL_D = 0.45        # projection of the vertical pilasters
PIL_W = 0.5
BAY_W = 6.6         # target structural bay width

BUILD_CONTEXT = False  # roads, neighbours, cars, trees: off while we focus on the building itself

# Gable walls (perpendicular to a wing) get a solid wall with one column of small windows.
END_EDGES = {frozenset(e) for e in [
    ('1944623862', '1944623858'), ('1944623880', '1944623872'),
    ('8158144803', '8158144804'), ('8158144801', '8158144802'),
    ('8158144799', '8158144800'), ('8158144797', '8158144798'),
]}
SIGN_EDGE = frozenset(('8158144801', '8158144802'))  # west wing gable, seen in ref.jpg
PENTHOUSE_EDGES = [  # (gable edge of the 10-storey part, distance inward, size along edge, size inward, height)
    (frozenset(('8158144801', '8158144802')), 9.0, 8.0, 7.0, 4.2),
    (frozenset(('8158144803', '8158144804')), 15.0, 10.0, 12.0, 3.6),
]


def level_top(lv):
    return 0.0 if lv <= 0 else GROUND_H + (lv - 1) * FLOOR_H
