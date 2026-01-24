"""NYC Subway station data and graph structure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Station:
    """Represents a subway station."""
    id: str
    name: str
    lines: list[str]
    gtfs_stop_id: str
    latitude: float
    longitude: float
    borough: str

    def __hash__(self):
        return hash(self.id)


# Major NYC subway stations with connections
# Format: id, name, lines, gtfs_stop_id, lat, lon, borough
STATIONS_DATA = [
    # Manhattan - Lower
    ("south_ferry", "South Ferry", ["1"], "142", 40.7019, -74.0130, "Manhattan"),
    ("whitehall", "Whitehall St-South Ferry", ["R", "W"], "R27", 40.7031, -74.0129, "Manhattan"),
    ("bowling_green", "Bowling Green", ["4", "5"], "420", 40.7046, -74.0140, "Manhattan"),
    ("wall_st_23", "Wall St", ["2", "3"], "137", 40.7069, -74.0100, "Manhattan"),
    ("wall_st_45", "Wall St", ["4", "5"], "418", 40.7074, -74.0090, "Manhattan"),
    ("fulton", "Fulton St", ["2", "3", "4", "5", "A", "C", "J", "Z"], "A38", 40.7102, -74.0079, "Manhattan"),
    ("park_place", "Park Place", ["2", "3"], "131", 40.7131, -74.0086, "Manhattan"),
    ("chambers_123", "Chambers St", ["1", "2", "3"], "130", 40.7150, -74.0093, "Manhattan"),
    ("chambers_ac", "Chambers St", ["A", "C"], "A32", 40.7143, -74.0083, "Manhattan"),
    ("city_hall", "City Hall", ["R", "W"], "R23", 40.7137, -74.0067, "Manhattan"),
    ("brooklyn_bridge", "Brooklyn Bridge-City Hall", ["4", "5", "6"], "416", 40.7133, -74.0041, "Manhattan"),
    ("canal_123", "Canal St", ["1", "2", "3"], "126", 40.7227, -74.0055, "Manhattan"),
    ("canal_ace", "Canal St", ["A", "C", "E"], "A34", 40.7209, -74.0051, "Manhattan"),
    ("canal_nqrw", "Canal St", ["N", "Q", "R", "W"], "R21", 40.7198, -74.0018, "Manhattan"),
    ("canal_jz", "Canal St", ["J", "Z"], "M20", 40.7184, -73.9999, "Manhattan"),
    ("canal_6", "Canal St", ["6"], "413", 40.7186, -74.0001, "Manhattan"),
    ("spring_6", "Spring St", ["6"], "414", 40.7225, -73.9973, "Manhattan"),
    ("spring_ce", "Spring St", ["C", "E"], "A33", 40.7263, -74.0039, "Manhattan"),
    ("houston", "Houston St", ["1"], "124", 40.7287, -74.0056, "Manhattan"),
    ("bleecker", "Bleecker St", ["6"], "D21", 40.7259, -73.9946, "Manhattan"),
    ("broadway_lafayette", "Broadway-Lafayette St", ["B", "D", "F", "M"], "D21", 40.7254, -73.9962, "Manhattan"),
    ("prince", "Prince St", ["N", "R", "W"], "R22", 40.7243, -73.9978, "Manhattan"),
    ("8th_nyu", "8th St-NYU", ["N", "R", "W"], "R20", 40.7306, -73.9924, "Manhattan"),
    ("astor_place", "Astor Place", ["6"], "D20", 40.7305, -73.9910, "Manhattan"),
    ("west_4th", "West 4th St-Washington Sq", ["A", "C", "E", "B", "D", "F", "M"], "A32", 40.7323, -74.0005, "Manhattan"),
    ("christopher", "Christopher St-Sheridan Sq", ["1"], "122", 40.7334, -74.0027, "Manhattan"),
    ("14th_123", "14th St", ["1", "2", "3"], "120", 40.7378, -74.0003, "Manhattan"),
    ("14th_fm", "14th St", ["F", "M"], "D17", 40.7382, -73.9997, "Manhattan"),
    ("14th_l_6th", "14th St", ["L"], "L01", 40.7379, -73.9968, "Manhattan"),
    ("union_sq", "14th St-Union Sq", ["4", "5", "6", "N", "Q", "R", "W", "L"], "R17", 40.7355, -73.9903, "Manhattan"),
    ("23rd_1", "23rd St", ["1"], "118", 40.7419, -74.0000, "Manhattan"),
    ("23rd_ce", "23rd St", ["C", "E"], "A30", 40.7459, -74.0002, "Manhattan"),
    ("23rd_fm", "23rd St", ["F", "M"], "D16", 40.7428, -73.9929, "Manhattan"),
    ("23rd_6", "23rd St", ["6"], "D18", 40.7394, -73.9864, "Manhattan"),
    ("23rd_nrw", "23rd St", ["N", "R", "W"], "R18", 40.7408, -73.9896, "Manhattan"),
    ("28th_1", "28th St", ["1"], "117", 40.7454, -73.9993, "Manhattan"),
    ("28th_6", "28th St", ["6"], "D19", 40.7431, -73.9842, "Manhattan"),
    ("28th_nrw", "28th St", ["N", "R", "W"], "R19", 40.7451, -73.9880, "Manhattan"),
    ("33rd_6", "33rd St", ["6"], "408", 40.7462, -73.9825, "Manhattan"),
    ("34th_penn_123", "34th St-Penn Station", ["1", "2", "3"], "115", 40.7507, -73.9912, "Manhattan"),
    ("34th_penn_ace", "34th St-Penn Station", ["A", "C", "E"], "A28", 40.7524, -73.9932, "Manhattan"),
    ("34th_herald", "34th St-Herald Sq", ["B", "D", "F", "M", "N", "Q", "R", "W"], "D14", 40.7496, -73.9879, "Manhattan"),
    ("42nd_times_sq", "Times Sq-42nd St", ["1", "2", "3", "7", "N", "Q", "R", "W", "S"], "R16", 40.7559, -73.9871, "Manhattan"),
    ("42nd_port_auth", "42nd St-Port Authority", ["A", "C", "E"], "A27", 40.7574, -73.9899, "Manhattan"),
    ("42nd_bryant", "42nd St-Bryant Park", ["B", "D", "F", "M"], "D13", 40.7545, -73.9847, "Manhattan"),
    ("grand_central", "Grand Central-42nd St", ["4", "5", "6", "7", "S"], "631", 40.7527, -73.9772, "Manhattan"),
    ("47_50_rock", "47-50 Sts-Rockefeller Ctr", ["B", "D", "F", "M"], "D15", 40.7586, -73.9812, "Manhattan"),
    ("49th", "49th St", ["N", "R", "W"], "R14", 40.7597, -73.9843, "Manhattan"),
    ("50th_1", "50th St", ["1"], "112", 40.7617, -73.9838, "Manhattan"),
    ("50th_ce", "50th St", ["C", "E"], "A25", 40.7621, -73.9858, "Manhattan"),
    ("51st", "51st St", ["6"], "D11", 40.7571, -73.9719, "Manhattan"),
    ("53rd_lex", "Lexington Av/53rd St", ["E", "M"], "629", 40.7576, -73.9693, "Manhattan"),
    ("5th_53rd", "5th Av/53rd St", ["E", "M"], "D12", 40.7602, -73.9753, "Manhattan"),
    ("57th_f", "57th St", ["F"], "B08", 40.7641, -73.9736, "Manhattan"),
    ("57th_nqrw", "57th St-7 Av", ["N", "Q", "R", "W"], "R13", 40.7645, -73.9804, "Manhattan"),
    ("59th_456", "59th St", ["4", "5", "6"], "D10", 40.7625, -73.9676, "Manhattan"),
    ("59th_nqrw", "Lexington Av/59th St", ["N", "R", "W"], "R11", 40.7629, -73.9673, "Manhattan"),
    ("59th_columbus", "59th St-Columbus Circle", ["1", "A", "C", "B", "D"], "A24", 40.7682, -73.9818, "Manhattan"),
    ("66th_lincoln", "66th St-Lincoln Center", ["1"], "108", 40.7734, -73.9822, "Manhattan"),
    ("72nd_123", "72nd St", ["1", "2", "3"], "107", 40.7787, -73.9820, "Manhattan"),
    ("72nd_bc", "72nd St", ["B", "C"], "A21", 40.7760, -73.9760, "Manhattan"),
    ("72nd_q", "72nd St", ["Q"], "Q04", 40.7690, -73.9583, "Manhattan"),
    ("77th", "77th St", ["6"], "D06", 40.7737, -73.9598, "Manhattan"),
    ("79th", "79th St", ["1"], "106", 40.7840, -73.9797, "Manhattan"),
    ("81st_museum", "81st St-Museum of Natural History", ["B", "C"], "A20", 40.7815, -73.9721, "Manhattan"),
    ("86th_456", "86th St", ["4", "5", "6"], "D05", 40.7794, -73.9555, "Manhattan"),
    ("86th_1", "86th St", ["1"], "105", 40.7888, -73.9770, "Manhattan"),
    ("86th_bc", "86th St", ["B", "C"], "A19", 40.7859, -73.9686, "Manhattan"),
    ("86th_q", "86th St", ["Q"], "Q03", 40.7779, -73.9516, "Manhattan"),
    ("96th_123", "96th St", ["1", "2", "3"], "104", 40.7937, -73.9723, "Manhattan"),
    ("96th_bc", "96th St", ["B", "C"], "A18", 40.7917, -73.9646, "Manhattan"),
    ("96th_q", "96th St", ["Q"], "Q02", 40.7844, -73.9472, "Manhattan"),
    ("96th_6", "96th St", ["6"], "D04", 40.7855, -73.9510, "Manhattan"),
    ("103rd_1", "103rd St", ["1"], "103", 40.7996, -73.9685, "Manhattan"),
    ("103rd_bc", "103rd St", ["B", "C"], "A17", 40.7967, -73.9613, "Manhattan"),
    ("103rd_6", "103rd St", ["6"], "D03", 40.7906, -73.9476, "Manhattan"),
    ("110th_1", "110th St-Cathedral Pkwy", ["1"], "A12", 40.8040, -73.9666, "Manhattan"),
    ("110th_bc", "110th St-Cathedral Pkwy", ["B", "C"], "A16", 40.8008, -73.9584, "Manhattan"),
    ("116th_1", "116th St-Columbia University", ["1"], "101", 40.8078, -73.9644, "Manhattan"),
    ("116th_bc", "116th St", ["B", "C"], "A15", 40.8050, -73.9548, "Manhattan"),
    ("116th_6", "116th St", ["6"], "D02", 40.7986, -73.9419, "Manhattan"),
    ("125th_1", "125th St", ["1"], "100", 40.8159, -73.9586, "Manhattan"),
    ("125th_abc", "125th St", ["A", "B", "C", "D"], "A14", 40.8109, -73.9523, "Manhattan"),
    ("125th_456", "125th St", ["4", "5", "6"], "D01", 40.8044, -73.9379, "Manhattan"),
    ("125th_23", "125th St", ["2", "3"], "224", 40.8077, -73.9453, "Manhattan"),
    ("135th_23", "135th St", ["2", "3"], "223", 40.8140, -73.9407, "Manhattan"),
    ("135th_bc", "135th St", ["B", "C"], "A13", 40.8143, -73.9476, "Manhattan"),
    ("137th", "137th St-City College", ["1"], "A11", 40.8223, -73.9537, "Manhattan"),
    ("145th_1", "145th St", ["1"], "A10", 40.8267, -73.9504, "Manhattan"),
    ("145th_3", "145th St", ["3"], "221", 40.8200, -73.9363, "Manhattan"),
    ("145th_acd", "145th St", ["A", "C", "D"], "A12", 40.8247, -73.9443, "Manhattan"),
    ("155th_ac", "155th St", ["A", "C"], "A11", 40.8305, -73.9383, "Manhattan"),
    ("155th_bd", "155th St", ["B", "D"], "D03", 40.8305, -73.9384, "Manhattan"),
    ("157th", "157th St", ["1"], "A09", 40.8340, -73.9448, "Manhattan"),
    ("163rd_1", "163rd St-Amsterdam Av", ["1"], "A08", 40.8360, -73.9400, "Manhattan"),
    ("168th_1", "168th St", ["1"], "A07", 40.8408, -73.9400, "Manhattan"),
    ("168th_ac", "168th St", ["A", "C"], "A09", 40.8408, -73.9400, "Manhattan"),
    ("175th", "175th St", ["A"], "A08", 40.8474, -73.9396, "Manhattan"),
    ("181st_1", "181st St", ["1"], "A06", 40.8498, -73.9337, "Manhattan"),
    ("181st_a", "181st St", ["A"], "A06", 40.8516, -73.9378, "Manhattan"),
    ("190th", "190th St", ["A"], "A05", 40.8590, -73.9329, "Manhattan"),
    ("191st", "191st St", ["1"], "A05", 40.8550, -73.9293, "Manhattan"),
    ("dyckman_1", "Dyckman St", ["1"], "A04", 40.8605, -73.9254, "Manhattan"),
    ("dyckman_a", "Dyckman St", ["A"], "A04", 40.8654, -73.9272, "Manhattan"),
    ("207th", "207th St", ["1"], "A03", 40.8647, -73.9188, "Manhattan"),
    ("215th", "215th St", ["1"], "A02", 40.8693, -73.9153, "Manhattan"),
    ("inwood_207", "Inwood-207th St", ["A"], "A02", 40.8680, -73.9197, "Manhattan"),

    # Brooklyn
    ("borough_hall", "Borough Hall", ["2", "3", "4", "5"], "235", 40.6940, -73.9900, "Brooklyn"),
    ("court_st", "Court St", ["R"], "R28", 40.6940, -73.9918, "Brooklyn"),
    ("jay_st", "Jay St-MetroTech", ["A", "C", "F", "R"], "R29", 40.6923, -73.9871, "Brooklyn"),
    ("hoyt_schermerhorn", "Hoyt-Schermerhorn Sts", ["A", "C", "G"], "A41", 40.6886, -73.9851, "Brooklyn"),
    ("hoyt_st", "Hoyt St", ["2", "3"], "236", 40.6904, -73.9850, "Brooklyn"),
    ("nevins", "Nevins St", ["2", "3", "4", "5"], "237", 40.6884, -73.9803, "Brooklyn"),
    ("atlantic_barclays", "Atlantic Av-Barclays Ctr", ["2", "3", "4", "5", "B", "D", "N", "Q", "R"], "D24", 40.6838, -73.9787, "Brooklyn"),
    ("bergen", "Bergen St", ["2", "3"], "238", 40.6861, -73.9751, "Brooklyn"),
    ("bergen_fg", "Bergen St", ["F", "G"], "F12", 40.6860, -73.9755, "Brooklyn"),
    ("grand_army", "Grand Army Plaza", ["2", "3"], "239", 40.6752, -73.9709, "Brooklyn"),
    ("eastern_pkwy", "Eastern Pkwy-Brooklyn Museum", ["2", "3"], "240", 40.6720, -73.9638, "Brooklyn"),
    ("franklin_av", "Franklin Av", ["2", "3", "4", "5"], "241", 40.6707, -73.9580, "Brooklyn"),
    ("nostrand", "Nostrand Av", ["3"], "242", 40.6699, -73.9504, "Brooklyn"),
    ("kingston_av", "Kingston Av", ["3"], "243", 40.6694, -73.9422, "Brooklyn"),
    ("crown_heights", "Crown Heights-Utica Av", ["3", "4"], "244", 40.6688, -73.9329, "Brooklyn"),
    ("sutter_4", "Sutter Av-Rutland Rd", ["4"], "246", 40.6651, -73.9226, "Brooklyn"),
    ("saratoga_3", "Saratoga Av", ["3"], "244", 40.6614, -73.9164, "Brooklyn"),
    ("rockaway_3", "Rockaway Av", ["3"], "243", 40.6621, -73.9089, "Brooklyn"),
    ("junius_3", "Junius St", ["3"], "242", 40.6634, -73.9023, "Brooklyn"),
    ("pennsylvania_3", "Pennsylvania Av", ["3"], "241", 40.6648, -73.8948, "Brooklyn"),
    ("van_siclen_3", "Van Siclen Av", ["3"], "240", 40.6655, -73.8893, "Brooklyn"),
    ("new_lots_3", "New Lots Av", ["3"], "239", 40.6663, -73.8844, "Brooklyn"),
    ("7th_av_fg", "7th Av", ["F", "G"], "F14", 40.6663, -73.9803, "Brooklyn"),
    ("15th_prospect", "15th St-Prospect Park", ["F", "G"], "F15", 40.6602, -73.9797, "Brooklyn"),
    ("church_ave_fg", "Church Av", ["F", "G"], "F16", 40.6501, -73.9798, "Brooklyn"),
    ("church_ave_25", "Church Av", ["2", "5"], "248", 40.6508, -73.9629, "Brooklyn"),
    ("beverley_rd", "Beverley Rd", ["2", "5"], "249", 40.6442, -73.9649, "Brooklyn"),
    ("newkirk_av_25", "Newkirk Av", ["2", "5"], "250", 40.6399, -73.9630, "Brooklyn"),
    ("flatbush_av", "Flatbush Av-Brooklyn College", ["2", "5"], "252", 40.6325, -73.9475, "Brooklyn"),
    ("kings_hwy_bq", "Kings Hwy", ["B", "Q"], "D35", 40.6088, -73.9574, "Brooklyn"),
    ("coney_island", "Coney Island-Stillwell Av", ["D", "F", "N", "Q"], "D43", 40.5774, -73.9812, "Brooklyn"),
    ("dekalb_av", "DeKalb Av", ["B", "Q", "R"], "R30", 40.6904, -73.9818, "Brooklyn"),
    ("bedford_nostrand", "Bedford-Nostrand Avs", ["G"], "G29", 40.6897, -73.9534, "Brooklyn"),
    ("classon_av", "Classon Av", ["G"], "G28", 40.6889, -73.9600, "Brooklyn"),
    ("clinton_wash", "Clinton-Washington Avs", ["G"], "G30", 40.6883, -73.9663, "Brooklyn"),
    ("fulton_g", "Fulton St", ["G"], "G31", 40.6872, -73.9753, "Brooklyn"),
    ("metropolitan_g", "Metropolitan Av", ["G"], "G26", 40.7126, -73.9514, "Brooklyn"),
    ("greenpoint_av", "Greenpoint Av", ["G"], "G26", 40.7313, -73.9543, "Brooklyn"),
    ("nassau_g", "Nassau Av", ["G"], "G28", 40.7246, -73.9512, "Brooklyn"),
    ("court_sq_g", "Court Sq", ["G"], "G22", 40.7467, -73.9459, "Queens"),
    ("broadway_g", "Broadway", ["G"], "G24", 40.7060, -73.9502, "Brooklyn"),
    ("lorimer_jm", "Lorimer St", ["J", "M"], "M11", 40.7038, -73.9474, "Brooklyn"),
    ("lorimer_g", "Lorimer St", ["G"], "G25", 40.7140, -73.9500, "Brooklyn"),
    ("marcy_av", "Marcy Av", ["J", "M", "Z"], "M12", 40.7084, -73.9577, "Brooklyn"),
    ("hewes", "Hewes St", ["J", "M"], "M13", 40.7069, -73.9534, "Brooklyn"),
    ("flushing_jm", "Flushing Av", ["J", "M"], "M14", 40.7004, -73.9411, "Brooklyn"),
    ("myrtle_wyckoff", "Myrtle-Wyckoff Avs", ["L", "M"], "L17", 40.6993, -73.9121, "Brooklyn"),
    ("jefferson_l", "Jefferson St", ["L"], "L18", 40.7066, -73.9228, "Brooklyn"),
    ("montrose_l", "Montrose Av", ["L"], "L15", 40.7073, -73.9399, "Brooklyn"),
    ("grand_l", "Grand St", ["L"], "L14", 40.7117, -73.9407, "Brooklyn"),
    ("graham_l", "Graham Av", ["L"], "L13", 40.7147, -73.9443, "Brooklyn"),
    ("lorimer_l", "Lorimer St", ["L"], "L12", 40.7140, -73.9500, "Brooklyn"),
    ("bedford_l", "Bedford Av", ["L"], "L10", 40.7177, -73.9566, "Brooklyn"),
    ("1st_av_l", "1st Av", ["L"], "L06", 40.7307, -73.9817, "Manhattan"),
    ("3rd_av_l", "3rd Av", ["L"], "L05", 40.7325, -73.9864, "Manhattan"),
    ("6th_av_l", "6th Av", ["L"], "L03", 40.7374, -73.9967, "Manhattan"),
    ("8th_av_l", "8th Av", ["L", "A", "C", "E"], "L02", 40.7399, -74.0024, "Manhattan"),
    ("williamsburg", "Marcy Av", ["J", "M", "Z"], "M12", 40.7084, -73.9577, "Brooklyn"),

    # Queens
    ("jackson_hts", "Jackson Hts-Roosevelt Av", ["7", "E", "F", "M", "R"], "G14", 40.7465, -73.8912, "Queens"),
    ("74th_broadway", "74th St-Broadway", ["7"], "705", 40.7468, -73.8912, "Queens"),
    ("queens_plaza", "Queens Plaza", ["E", "M", "R"], "G21", 40.7489, -73.9372, "Queens"),
    ("court_sq_em", "Court Sq", ["E", "M"], "F09", 40.7477, -73.9453, "Queens"),
    ("court_sq_7", "Court Sq", ["7"], "719", 40.7470, -73.9458, "Queens"),
    ("hunters_point", "Hunters Point Av", ["7"], "720", 40.7423, -73.9487, "Queens"),
    ("vernon_jackson", "Vernon Blvd-Jackson Av", ["7"], "721", 40.7427, -73.9535, "Queens"),
    ("queensboro_plaza", "Queensboro Plaza", ["7", "N", "W"], "R09", 40.7507, -73.9403, "Queens"),
    ("astoria_ditmars", "Astoria-Ditmars Blvd", ["N", "W"], "R01", 40.7752, -73.9120, "Queens"),
    ("astoria_blvd", "Astoria Blvd", ["N", "W"], "R03", 40.7700, -73.9179, "Queens"),
    ("30th_av", "30th Av", ["N", "W"], "R04", 40.7669, -73.9214, "Queens"),
    ("broadway_nw", "Broadway", ["N", "W"], "R05", 40.7614, -73.9256, "Queens"),
    ("36th_av", "36th Av", ["N", "W"], "R06", 40.7567, -73.9299, "Queens"),
    ("39th_av", "39th Av", ["N", "W"], "R07", 40.7527, -73.9326, "Queens"),
    ("steinway", "Steinway St", ["M", "R"], "G19", 40.7561, -73.9205, "Queens"),
    ("46th_st", "46th St", ["M", "R"], "G18", 40.7567, -73.9133, "Queens"),
    ("65th_st", "65th St", ["M", "R"], "G16", 40.7494, -73.8982, "Queens"),
    ("northern_blvd", "Northern Blvd", ["M", "R"], "G17", 40.7529, -73.9063, "Queens"),
    ("woodhaven_blvd", "Woodhaven Blvd", ["M", "R"], "G15", 40.7455, -73.8519, "Queens"),
    ("elmhurst_av", "Elmhurst Av", ["M", "R"], "G14", 40.7427, -73.8822, "Queens"),
    ("63rd_drive", "63rd Dr-Rego Park", ["M", "R"], "G12", 40.7297, -73.8616, "Queens"),
    ("67th_av", "67th Av", ["M", "R"], "G11", 40.7264, -73.8530, "Queens"),
    ("forest_hills", "Forest Hills-71st Av", ["E", "F", "M", "R"], "G08", 40.7216, -73.8446, "Queens"),
    ("kew_gardens", "Kew Gardens-Union Tpke", ["E", "F"], "F06", 40.7140, -73.8311, "Queens"),
    ("briarwood", "Briarwood", ["E", "F"], "F05", 40.7090, -73.8206, "Queens"),
    ("parsons_blvd", "Parsons Blvd", ["F"], "F04", 40.7073, -73.8032, "Queens"),
    ("sutphin_blvd", "Sutphin Blvd", ["F"], "F03", 40.7053, -73.8103, "Queens"),
    ("jamaica_179", "Jamaica-179th St", ["F"], "F01", 40.7126, -73.7838, "Queens"),
    ("jamaica_center", "Jamaica Center-Parsons/Archer", ["E", "J", "Z"], "G05", 40.7021, -73.8008, "Queens"),
    ("sutphin_archer", "Sutphin Blvd-Archer Av-JFK", ["E", "J", "Z"], "G06", 40.7005, -73.8072, "Queens"),
    ("flushing_main", "Flushing-Main St", ["7"], "701", 40.7596, -73.8300, "Queens"),
    ("mets_willets", "Mets-Willets Point", ["7"], "702", 40.7543, -73.8456, "Queens"),
    ("111th_st", "111th St", ["7"], "703", 40.7517, -73.8553, "Queens"),
    ("103rd_corona", "103rd St-Corona Plaza", ["7"], "704", 40.7497, -73.8627, "Queens"),
    ("junction_blvd", "Junction Blvd", ["7"], "706", 40.7492, -73.8696, "Queens"),
    ("90th_elmhurst", "90th St-Elmhurst Av", ["7"], "707", 40.7484, -73.8760, "Queens"),
    ("82nd_jackson", "82nd St-Jackson Hts", ["7"], "708", 40.7474, -73.8839, "Queens"),
    ("69th_fisk", "69th St", ["7"], "709", 40.7464, -73.8962, "Queens"),
    ("61st_woodside", "61st St-Woodside", ["7"], "710", 40.7456, -73.9029, "Queens"),
    ("52nd_lincoln", "52nd St", ["7"], "711", 40.7442, -73.9123, "Queens"),
    ("46th_bliss", "46th St-Bliss St", ["7"], "712", 40.7434, -73.9187, "Queens"),
    ("40th_lowery", "40th St-Lowery St", ["7"], "713", 40.7435, -73.9240, "Queens"),
    ("33rd_rawson", "33rd St-Rawson St", ["7"], "714", 40.7449, -73.9307, "Queens"),

    # Bronx
    ("3rd_av_149", "3rd Av-149th St", ["2", "5"], "204", 40.8161, -73.9176, "Bronx"),
    ("149th_grand", "149th St-Grand Concourse", ["2", "4", "5"], "205", 40.8185, -73.9273, "Bronx"),
    ("138th_grand", "138th St-Grand Concourse", ["4", "5"], "402", 40.8132, -73.9300, "Bronx"),
    ("yankee_stadium", "161st St-Yankee Stadium", ["4", "B", "D"], "D10", 40.8279, -73.9257, "Bronx"),
    ("167th", "167th St", ["4"], "404", 40.8355, -73.9217, "Bronx"),
    ("170th", "170th St", ["4"], "405", 40.8398, -73.9175, "Bronx"),
    ("176th", "176th St", ["4"], "406", 40.8484, -73.9117, "Bronx"),
    ("burnside", "Burnside Av", ["4"], "407", 40.8532, -73.9074, "Bronx"),
    ("183rd", "183rd St", ["4"], "408", 40.8582, -73.9035, "Bronx"),
    ("fordham_4", "Fordham Rd", ["4"], "409", 40.8627, -73.9010, "Bronx"),
    ("kingsbridge", "Kingsbridge Rd", ["4"], "410", 40.8676, -73.8975, "Bronx"),
    ("bedford_park_4", "Bedford Park Blvd", ["4"], "411", 40.8730, -73.8902, "Bronx"),
    ("mosholu", "Mosholu Pkwy", ["4"], "412", 40.8790, -73.8849, "Bronx"),
    ("woodlawn", "Woodlawn", ["4"], "401", 40.8862, -73.8786, "Bronx"),
    ("tremont_bd", "Tremont Av", ["B", "D"], "D07", 40.8503, -73.9055, "Bronx"),
    ("182nd_183rd", "182nd-183rd Sts", ["B", "D"], "D06", 40.8566, -73.9007, "Bronx"),
    ("fordham_bd", "Fordham Rd", ["B", "D"], "D05", 40.8612, -73.8980, "Bronx"),
    ("kingsbridge_bd", "Kingsbridge Rd", ["B", "D"], "D04", 40.8672, -73.8933, "Bronx"),
    ("bedford_park_bd", "Bedford Park Blvd-Lehman College", ["B", "D"], "D03", 40.8731, -73.8898, "Bronx"),
    ("norwood_205", "Norwood-205th St", ["D"], "D01", 40.8749, -73.8791, "Bronx"),
    ("pelham_pkwy", "Pelham Pkwy", ["2", "5"], "215", 40.8572, -73.8676, "Bronx"),
    ("bronx_park_east", "Bronx Park East", ["2", "5"], "216", 40.8489, -73.8684, "Bronx"),
    ("allerton", "Allerton Av", ["2", "5"], "217", 40.8656, -73.8677, "Bronx"),
    ("burke_av", "Burke Av", ["2", "5"], "218", 40.8714, -73.8673, "Bronx"),
    ("gun_hill", "Gun Hill Rd", ["2", "5"], "219", 40.8778, -73.8664, "Bronx"),
    ("219th", "219th St", ["2", "5"], "220", 40.8833, -73.8626, "Bronx"),
    ("225th", "225th St", ["2", "5"], "221", 40.8883, -73.8604, "Bronx"),
    ("233rd", "233rd St", ["2", "5"], "222", 40.8932, -73.8573, "Bronx"),
    ("nereid", "Nereid Av", ["2", "5"], "223", 40.8985, -73.8546, "Bronx"),
    ("wakefield_241", "Wakefield-241st St", ["2"], "201", 40.9032, -73.8507, "Bronx"),
    ("eastchester_dyre", "Eastchester-Dyre Av", ["5"], "501", 40.8885, -73.8308, "Bronx"),
    ("baychester", "Baychester Av", ["5"], "502", 40.8785, -73.8385, "Bronx"),
    ("gun_hill_5", "Gun Hill Rd", ["5"], "503", 40.8694, -73.8463, "Bronx"),
    ("morris_park", "Morris Park", ["5"], "504", 40.8545, -73.8602, "Bronx"),
    ("pelham_bay", "Pelham Bay Park", ["6"], "601", 40.8523, -73.8282, "Bronx"),
    ("buhre", "Buhre Av", ["6"], "602", 40.8467, -73.8325, "Bronx"),
    ("middletown", "Middletown Rd", ["6"], "603", 40.8439, -73.8364, "Bronx"),
    ("westchester_sq", "Westchester Sq-E Tremont Av", ["6"], "604", 40.8394, -73.8427, "Bronx"),
    ("zerega", "Zerega Av", ["6"], "605", 40.8366, -73.8471, "Bronx"),
    ("castle_hill", "Castle Hill Av", ["6"], "606", 40.8343, -73.8512, "Bronx"),
    ("parkchester", "Parkchester", ["6"], "607", 40.8332, -73.8607, "Bronx"),
    ("st_lawrence", "St Lawrence Av", ["6"], "608", 40.8315, -73.8676, "Bronx"),
    ("morrison_soundview", "Morrison Av-Soundview", ["6"], "609", 40.8295, -73.8745, "Bronx"),
    ("elder_av", "Elder Av", ["6"], "610", 40.8287, -73.8792, "Bronx"),
    ("whitlock", "Whitlock Av", ["6"], "611", 40.8266, -73.8862, "Bronx"),
    ("hunts_point", "Hunts Point Av", ["6"], "612", 40.8206, -73.8905, "Bronx"),
    ("longwood", "Longwood Av", ["6"], "613", 40.8162, -73.8962, "Bronx"),
    ("e_149th", "E 149th St", ["6"], "614", 40.8120, -73.9042, "Bronx"),
    ("e_143rd", "E 143rd St-St Mary's St", ["6"], "615", 40.8088, -73.9076, "Bronx"),
    ("cypress_av", "Cypress Av", ["6"], "616", 40.8054, -73.9140, "Bronx"),
    ("brook_av", "Brook Av", ["6"], "617", 40.8074, -73.9191, "Bronx"),
    ("3rd_av_138", "3rd Av-138th St", ["6"], "618", 40.8101, -73.9262, "Bronx"),
]

# Build station objects
STATIONS = {}
for data in STATIONS_DATA:
    station = Station(
        id=data[0],
        name=data[1],
        lines=data[2],
        gtfs_stop_id=data[3],
        latitude=data[4],
        longitude=data[5],
        borough=data[6]
    )
    STATIONS[station.id] = station

# Build lookup by name (case-insensitive, partial match)
STATION_NAME_INDEX: dict[str, Station] = {}
for station in STATIONS.values():
    name_lower = station.name.lower()
    STATION_NAME_INDEX[name_lower] = station
    # Also index without "St", "Av", etc.
    for word in ["st", "av", "ave", "blvd", "rd", "pkwy"]:
        simplified = name_lower.replace(f" {word}", "").replace(f"-{word}", "")
        if simplified != name_lower:
            STATION_NAME_INDEX[simplified] = station

# Common aliases for popular stations
STATION_ALIASES: dict[str, str] = {
    "times square": "42nd_times_sq",
    "times sq": "42nd_times_sq",
    "42nd st": "42nd_times_sq",
    "grand central": "grand_central",
    "penn station": "34th_penn_123",
    "penn": "34th_penn_123",
    "herald square": "34th_herald",
    "herald sq": "34th_herald",
    "union square": "union_sq",
    "union sq": "union_sq",
    "columbus circle": "59th_columbus",
    "port authority": "42nd_port_auth",
    "world trade center": "fulton",
    "wtc": "fulton",
    "brooklyn bridge": "brooklyn_bridge",
    "city hall": "city_hall",
    "atlantic terminal": "atlantic_barclays",
    "barclays": "atlantic_barclays",
    "barclays center": "atlantic_barclays",
    "yankee stadium": "yankee_stadium",
    "flushing": "flushing_main",
    "main street flushing": "flushing_main",
    "jamaica": "jamaica_center",
    "coney island": "coney_island",
    "prospect park": "15th_prospect",
    "museum of natural history": "81st_museum",
    "lincoln center": "66th_lincoln",
    "columbia": "116th_1",
    "columbia university": "116th_1",
    "nyu": "8th_nyu",
    "astor place": "astor_place",
    "bleecker": "bleecker",
    "west 4th": "west_4th",
    "west fourth": "west_4th",
    "washington square": "west_4th",
    "canal street": "canal_nqrw",
    "canal st": "canal_nqrw",
    "fulton street": "fulton",
    "fulton st": "fulton",
    "chambers street": "chambers_123",
    "chambers st": "chambers_123",
    "14th street": "union_sq",
    "14th st": "union_sq",
    "23rd street": "23rd_1",
    "23rd st": "23rd_1",
    "34th street": "34th_herald",
    "34th st": "34th_herald",
    "42nd street": "42nd_times_sq",
    "59th street": "59th_columbus",
    "59th st": "59th_columbus",
    "72nd street": "72nd_123",
    "72nd st": "72nd_123",
    "86th street": "86th_1",
    "86th st": "86th_1",
    "96th street": "96th_123",
    "96th st": "96th_123",
    "125th street": "125th_1",
    "125th st": "125th_1",
    "harlem": "125th_abc",
    "jackson heights": "jackson_hts",
    "forest hills": "forest_hills",
    "rockefeller center": "47_50_rock",
    "rockefeller": "47_50_rock",
    "rock center": "47_50_rock",
    "bryant park": "42nd_bryant",
    "lexington": "59th_456",
    "lex": "59th_456",
}


def find_station(query: str) -> Optional[Station]:
    """Find a station by name (fuzzy match)."""
    query_lower = query.lower().strip()

    # Check aliases first
    if query_lower in STATION_ALIASES:
        return STATIONS.get(STATION_ALIASES[query_lower])

    # Exact match
    if query_lower in STATION_NAME_INDEX:
        return STATION_NAME_INDEX[query_lower]

    # Partial match - prefer shorter station names (more specific)
    matches = []
    for name, station in STATION_NAME_INDEX.items():
        if query_lower in name or name in query_lower:
            matches.append((len(name), station))

    if matches:
        matches.sort(key=lambda x: x[0])
        return matches[0][1]

    # Check station IDs
    for station_id, station in STATIONS.items():
        if query_lower in station_id:
            return station

    return None


def find_stations_by_line(line: str) -> list[Station]:
    """Find all stations on a given line."""
    line = line.upper()
    return [s for s in STATIONS.values() if line in s.lines]


def get_station_lines(station_id: str) -> list[str]:
    """Get all lines serving a station."""
    station = STATIONS.get(station_id)
    return station.lines if station else []
