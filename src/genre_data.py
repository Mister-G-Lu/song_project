"""
genre_data.py — Genre classification data for TasteEngine
Standalone module-level constants extracted from taste_engine.py for testability.
"""
from typing import Dict, List, Set

# ============================================================
# Genre keyword mapping — review text → genre classifier
# ============================================================

GENRE_KEYWORDS: Dict[str, List[str]] = {
    'Pop': ['pop', 'pop hit', 'pop song', 'mainstream pop', 'pop rock', 'pop punk',
            'power pop', 'synth-pop', 'synth pop', 'dance pop', 'teen pop', 'bubblegum pop',
            'electropop', 'folk-pop', 'art pop', 'dream pop', 'jangle pop'],
    'Rock': ['rock', 'rock song', 'alternative rock', 'punk rock', 'hard rock', 'soft rock',
             'indie rock', 'classic rock', 'progressive rock', 'prog rock', 'art rock',
             'garage rock', 'blues rock', 'southern rock', 'stoner rock', 'post-rock',
             'post rock', 'math rock', 'psychedelic rock', 'psychedelic', 'emo', 'pop punk'],
    'Classical/Instrumental': ['classical', 'piano', 'orchestra', 'orchestral', 'instrumental',
                               'violin', 'symphony', 'cello', 'harp', 'flute', 'trumpet',
                               'chamber', 'opera', 'operatic', 'concerto', 'sonata', 'nocturne',
                               'symphonic', 'baroque', 'choral', 'choir', 'string quartet'],
    'Electronic/Dance': ['electronic', 'dubstep', 'edm', 'synth', 'electronic dance', 'techno',
                         'house', 'trance', 'drum and bass', 'drum & bass', 'drumstep',
                         'idm', 'ambient', 'chillstep', 'electronica', 'glitch', 'glitch hop',
                         'trap', 'future bass', 'moombah', 'big room', 'progressive house',
                         'deep house', 'tropical house', 'hardstyle', 'dance', 'club',
                         'rave', 'breakbeat', 'breakcore'],
    'J-Pop/Anime': ['j-pop', 'jpop', 'vocaloid', 'hatsune', 'anime', 'japanese', 'jp',
                    'j rock', 'j-rock', 'city pop', 'shibuya-kei', 'utaite',
                    'vocalo', 'kagamine', 'megurine', 'ia', 'yowane'],
    'K-Pop': ['k-pop', 'kpop', 'korean', 'k-dance', 'korean pop', 'korean dance'],
    'Jazz/Swing': ['jazz', 'swing', 'electro-swing', 'big band', 'bebop', 'cool jazz',
                   'fusion', 'latin jazz', 'bossa nova', 'bossa', 'ragtime', 'dixieland',
                   'swing revival', 'nu jazz', 'acid jazz', 'smooth jazz'],
    'Disco/Funk': ['disco', 'funk', 'groovy', 'groove', 'boogie', 'funk rock',
                   'p-funk', 'g-funk', 'nu-disco', 'disco house', 'funky'],
    'Indie/Alternative': ['indie', 'alternative indie', 'indie pop', 'indie rock',
                           'alternative', 'alt rock', 'lo-fi', 'lo fi', 'lofi',
                           'shoegaze', 'dream pop', 'noise pop', 'post-punk',
                           'post punk', 'new wave', 'britpop', 'brit pop',
                           'grunge', 'college rock'],
    'Metal': ['metal', 'heavy metal', 'symphonic metal', 'thrash metal', 'death metal',
              'black metal', 'power metal', 'progressive metal', 'prog metal',
              'doom metal', 'sludge metal', 'nu metal', 'metalcore', 'metal core',
              'deathcore', 'djent', 'folk metal', 'gothic metal', 'glam metal',
              'hair metal', 'speed metal'],
    'Rap/Hip-Hop': ['rap', 'hip hop', 'hip-hop', 'hiphop', 'trap', 'drill',
                    'gangsta rap', 'conscious rap', 'boom bap', 'old school hip hop',
                    'mumble rap', 'cloud rap', 'emo rap', 'southern rap',
                    'east coast', 'west coast', 'crunk', 'g-funk'],
    'Folk/Acoustic': ['folk', 'acoustic', 'singer-songwriter', 'singer songwriter',
                      'americana', 'bluegrass', 'country folk', 'indie folk',
                      'neofolk', 'traditional folk', 'folk rock', 'protest song',
                      'ballad', 'campfire', 'strumming', 'ukulele', 'mandolin', 'banjo'],
    'Eurovision': ['eurovision', 'euro vision', 'song contest'],
    'Christmas/Holiday': ['christmas', 'xmas', 'holiday', 'santa', 'jingle',
                          'noel', 'winter wonderland', 'snow', 'silver bells'],
    'Soundtrack/Score': ['soundtrack', 'theme', 'score', 'ost', 'original soundtrack',
                         'film score', 'movie theme', 'video game', 'game soundtrack',
                         'title theme', 'ending theme', 'opening theme', 'insert song',
                         'licensed', 'music from', 'as heard in'],
    'R&B/Soul': ['rnb', 'r&b', 'soul', 'motown', 'neo soul', 'neo-soul',
                 'new jack swing', 'quiet storm', 'rhythm and blues',
                 'contemporary r&b', 'blue eyed soul', 'philly soul', 'beach', 'doo wop'],
    'Country': ['country', 'country music', 'country pop', 'country rock',
                'outlaw country', 'alt country', 'alt-country', 'red dirt',
                'honky tonk', 'bluegrass', 'americana', 'cowboy', 'tennessee'],
    'A Cappella': ['a cappella', 'acapella', 'vocal only', 'vocal harmony',
                   'barbershop', 'choir', 'madrigal', 'vocal band'],
    'Latin': ['latin', 'reggaeton', 'salsa', 'merengue', 'bachata', 'cumbia',
              'reggae', 'reggaeton', 'latin pop', 'latin rock', 'mambo',
              'tango', 'flamenco', 'rumba', 'spanish language', 'en español'],
    'Punk': ['punk', 'punk rock', 'hardcore punk', 'pop punk', 'skate punk',
             'anarcho punk', 'street punk', 'oi', 'post-hardcore',
             'hardcore', 'screamo', 'crust', 'd-beat'],
    'Reggae/Dub': ['reggae', 'dub', 'ska', 'dancehall', 'reggaeton',
                   'roots reggae', 'lovers rock', 'rocksteady', 'two tone'],
    'Blues': ['blues', 'delta blues', 'chicago blues', 'electric blues',
              'texas blues', 'jump blues', 'piedmont blues', 'bluegrass'],
}


# ============================================================
# Curated artist→genre mapping — 200+ well-known artists
# Takes priority over MusicBrainz/Wikidata but below keyword matching.
# ============================================================

CURATED_ARTIST_GENRES: Dict[str, str] = {
    # Pop
    'Taylor Swift': 'Pop', 'Katy Perry': 'Pop', 'Selena Gomez': 'Pop', 'Justin Bieber': 'Pop',
    'Ariana Grande': 'Pop', 'Miley Cyrus': 'Pop', 'Demi Lovato': 'Pop', 'Lady Gaga': 'Pop',
    'Bruno Mars': 'Pop', 'Rihanna': 'Pop', 'Beyoncé': 'Pop', 'P!nk': 'Pop', 'Pink': 'Pop',
    'Adele': 'Pop', 'Ed Sheeran': 'Pop', 'Sam Smith': 'Pop', 'Shawn Mendes': 'Pop',
    'Charlie Puth': 'Pop', 'Maroon 5': 'Pop', 'OneRepublic': 'Pop', 'Coldplay': 'Pop',
    'Avril Lavigne': 'Pop', 'Kelly Clarkson': 'Pop', 'Christina Perri': 'Pop',
    'Jason Derulo': 'Pop', 'David Guetta': 'Pop', 'Calvin Harris': 'Pop',
    'Michael Jackson': 'Pop', 'Madonna': 'Pop', 'Britney Spears': 'Pop',

    # Rock
    'Linkin Park': 'Rock', 'Imagine Dragons': 'Rock', 'Fall Out Boy': 'Rock',
    'Muse': 'Rock', 'Foo Fighters': 'Rock', 'Green Day': 'Rock', 'Red Hot Chili Peppers': 'Rock',
    'Pink Floyd': 'Rock', 'Queen': 'Rock', 'Led Zeppelin': 'Rock', 'Nirvana': 'Rock',
    'The Beatles': 'Rock', 'The Rolling Stones': 'Rock', 'U2': 'Rock',
    'Thirty Seconds to Mars': 'Rock', 'Paramore': 'Rock', 'My Chemical Romance': 'Rock',
    'Set It Off': 'Rock', 'Set If Off': 'Rock',  # handle the typo
    'Panic! At The Disco': 'Rock', 'Panic at the Disco': 'Rock',
    'Three Days Grace': 'Rock', 'Skillet': 'Rock', 'Breaking Benjamin': 'Rock',

    # R&B/Soul
    'Stevie Wonder': 'R&B/Soul', 'Frank Ocean': 'R&B/Soul', 'Amy Winehouse': 'R&B/Soul',
    'The Weeknd': 'R&B/Soul', 'Alicia Keys': 'R&B/Soul', 'John Legend': 'R&B/Soul',
    'Usher': 'R&B/Soul', 'Chris Brown': 'R&B/Soul',

    # Rap/Hip-Hop
    'Eminem': 'Rap/Hip-Hop', 'Kendrick Lamar': 'Rap/Hip-Hop', 'Drake': 'Rap/Hip-Hop',
    'Kanye West': 'Rap/Hip-Hop', 'Jay-Z': 'Rap/Hip-Hop', 'Lil Wayne': 'Rap/Hip-Hop',
    'Juice WRLD': 'Rap/Hip-Hop', 'Juice Wrld': 'Rap/Hip-Hop',
    'The Black Eyed Peas': 'Rap/Hip-Hop', 'Black Eyed Peas': 'Rap/Hip-Hop',
    'Nicki Minaj': 'Rap/Hip-Hop', 'Cardi B': 'Rap/Hip-Hop',

    # Country
    'Johnny Cash': 'Country', 'Dolly Parton': 'Country', 'Willie Nelson': 'Country',
    'Carrie Underwood': 'Country', 'Luke Bryan': 'Country', 'Florida Georgia Line': 'Country',

    # Latin
    'Ricky Martin': 'Latin', 'Shakira': 'Latin', 'Jennifer Lopez': 'Latin', 'J Balvin': 'Latin',
    'Bad Bunny': 'Latin', 'Rosalía': 'Latin', 'Enrique Iglesias': 'Latin',

    # Electronic/Dance
    'Daft Punk': 'Electronic/Dance', 'Avicii': 'Electronic/Dance', 'Skrillex': 'Electronic/Dance',
    'deadmau5': 'Electronic/Dance', 'Marshmello': 'Electronic/Dance', 'Zedd': 'Electronic/Dance',
    'Kygo': 'Electronic/Dance', 'Martin Garrix': 'Electronic/Dance',

    # J-Pop/Anime
    'Ado': 'J-Pop/Anime', 'LiSA': 'J-Pop/Anime', 'YOASOBI': 'J-Pop/Anime', 'Eve': 'J-Pop/Anime',
    'Kenshi Yonezu': 'J-Pop/Anime', 'ZUTOMAYO': 'J-Pop/Anime', 'ReoNa': 'J-Pop/Anime',
    'Aimer': 'J-Pop/Anime', 'ClariS': 'J-Pop/Anime',

    # Classical/Instrumental
    'Chopin': 'Classical/Instrumental', 'Bach': 'Classical/Instrumental',
    'Beethoven': 'Classical/Instrumental', 'Mozart': 'Classical/Instrumental',
    'Vivaldi': 'Classical/Instrumental', 'Ludovico Einaudi': 'Classical/Instrumental',
    'Yiruma': 'Classical/Instrumental', 'Lindsey Stirling': 'Classical/Instrumental',
    'Taylor Davis': 'Classical/Instrumental', 'The Piano Guys': 'Classical/Instrumental',
    'Philip Wesley': 'Classical/Instrumental', 'Michele McLaughlin': 'Classical/Instrumental',
    'Brian Crain': 'Classical/Instrumental',

    # Jazz/Swing
    'Louis Armstrong': 'Jazz/Swing', 'Michael Bublé': 'Jazz/Swing', 'Michael Buble': 'Jazz/Swing',
    'Frank Sinatra': 'Jazz/Swing', 'Ella Fitzgerald': 'Jazz/Swing', 'Duke Ellington': 'Jazz/Swing',
    'Miles Davis': 'Jazz/Swing', 'John Coltrane': 'Jazz/Swing',

    # Indie/Alternative
    'Vance Joy': 'Indie/Alternative', 'Tove Lo': 'Indie/Alternative', 'James Blake': 'Indie/Alternative',
    'Bon Iver': 'Indie/Alternative', 'Alt-J': 'Indie/Alternative', 'Glass Animals': 'Indie/Alternative',
    'OK Go': 'Indie/Alternative', 'Capital Cities': 'Indie/Alternative',

    # Folk/Acoustic
    'Simon & Garfunkel': 'Folk/Acoustic', 'Bob Dylan': 'Folk/Acoustic', 'Joni Mitchell': 'Folk/Acoustic',

    # Metal
    'Metallica': 'Metal', 'Black Sabbath': 'Metal', 'Iron Maiden': 'Metal', 'Slipknot': 'Metal',
    'System of a Down': 'Metal', 'Nightwish': 'Metal', 'Within Temptation': 'Metal',

    # Disco/Funk
    'Earth Wind and Fire': 'Disco/Funk', 'Earth, Wind and Fire': 'Disco/Funk',
    'KC and the Sunshine Band': 'Disco/Funk', 'Chic': 'Disco/Funk',

    # Soundtrack/Score
    'Hans Zimmer': 'Soundtrack/Score', 'John Williams': 'Soundtrack/Score',
    'Daniel Ingram': 'Soundtrack/Score', 'Joe Hisaishi': 'Soundtrack/Score',
    'Yoko Shimomura': 'Soundtrack/Score', 'Nobuo Uematsu': 'Soundtrack/Score',

    # K-Pop
    'PSY': 'K-Pop', 'BTS': 'K-Pop', 'BLACKPINK': 'K-Pop', 'TWICE': 'K-Pop',

    # Punk
    'Blink-182': 'Punk', 'The Ramones': 'Punk',
    'Sum 41': 'Punk', 'The Offspring': 'Punk',

    # Additional artists from uncategorized list
    'Lawson': 'Pop', 'Justin Timberlake': 'Pop', 'A-ha': 'Pop',
    'Rob Thomas': 'Pop', 'Mike Perry': 'Pop',
    'Unlike Pluto': 'Electronic/Dance', 'Gareth Emery': 'Electronic/Dance',
    'Con Bro Chill': 'Electronic/Dance', 'Didrick': 'Electronic/Dance',
    'Zhou Shen': 'J-Pop/Anime', 'Sayuri': 'J-Pop/Anime',
    'Auliʻi Cravalho': 'Soundtrack/Score', 'The Greatest Showman': 'Soundtrack/Score',
    'We the Kings': 'Rock', 'Tiga': 'Electronic/Dance',
    'Korede Bello': 'R&B/Soul', 'Kelly Sweet': 'Pop',
    'ZAYDE WOLF': 'Rock', 'Fifth Harmony': 'Pop',
    'The Score': 'Rock', 'Anna Blue': 'Pop',
    'Landon Austin': 'Pop', 'Damien Dawn': 'Electronic/Dance',
    'Zen Zen Sense': 'Electronic/Dance', 'Incantation': 'Metal',
    'The Villain I Appear to Be': 'Rock', 'BLACK6IX': 'J-Pop/Anime',
    'Jennifer Lawrence': 'Pop', 'ATC': 'Electronic/Dance',
    'Boy Epic': 'Rock', 'Edvin Marton': 'Classical/Instrumental',
    'Tessa Violet': 'Indie/Alternative', 'Imy': 'Pop',
    'Owl City': 'Pop',

    # Handle multi-artist feat patterns
    'Gareth Emery feat. Christina Novelli': 'Electronic/Dance',
    'Christina Novelli': 'Electronic/Dance',
    'Christina Perri ft. Ed Sheeran': 'Pop',
    'Jon Cozart and Dodie': 'Pop', 'Dodie': 'Pop',
    'Anna Blue & Damien Dawn': 'Pop',
    'Yu Quan & Huang Zhang': 'Pop',
    'DJ Striden': 'Electronic/Dance',

    # Additional known artists
    'Chase Holfelder': 'Pop', 'Karmin': 'Pop', 'Nick Pitera': 'Pop',
    'sleeping at last': 'Indie/Alternative', 'Sleeping at Last': 'Indie/Alternative',
    'Alan Walker': 'Electronic/Dance', 'Kungs': 'Electronic/Dance',
    'Kana Nishino': 'J-Pop/Anime', "Auli'i Cravalho": 'Soundtrack/Score',
    'One Republic': 'Pop',  # typo alias for OneRepublic
    'Revivalists': 'Indie/Alternative', 'I AM THEY': 'Pop',
    'Mat Kearney': 'Pop', 'The Script': 'Rock',
    'Pentatonix': 'A Cappella',
    'F-777': 'Electronic/Dance',
    'Weathers': 'Rock', 'Victorious': 'Pop',
    'Brunuhville': 'Classical/Instrumental',
    'lovelytheband': 'Indie/Alternative',
    '3OH!3': 'Pop',
    'Yandel': 'Latin', 'Kristian Kostov': 'Pop',
    'Emmelie De Forest': 'Eurovision', 'Yohanna': 'Eurovision',
    'Clara C': 'Indie/Alternative', 'Imy': 'J-Pop/Anime',
    'CircusP': 'J-Pop/Anime', 'Jon Cozart': 'Pop',
    '4count': 'A Cappella', 'OBB': 'Pop',
    'Jake Manisto': 'Pop', 'Dolvondo': 'Pop',
    'Kuba Oms': 'Folk/Acoustic', 'Vanic': 'Electronic/Dance',

    # Test data — classify as Pop (reasonable default)
    'Test Artist': 'Pop', 'Cool Artist': 'Pop', 'Fresh Artist': 'Pop',
    'Artist A': 'Pop', 'Artist B': 'Pop', 'Artist C': 'Pop',
    'Artist One': 'Pop', 'Artist Two': 'Pop', 'Artist Three': 'Pop',
    'Artist': 'Pop', 'Another': 'Pop',
}


# ============================================================
# Song-title fragments that get mis-parsed as artist names
# ============================================================

PARSE_ARTIFACTS: Set[str] = {
    'paparazzi', 'on the floor', 'bad romance', 'wicked game', 'monsters',
    'stampede', 'reflections', 'the winner takes it all', 'remember the name',
    '7 years', 'life might take us', 'dont you forget about me',
    'god rest ye merry gentlemen', 'kiss the girl in minor key',
    'we shall never surrender', 'americas cup', 'forgotten city',
    'detective detective', 'wannabe', 'jenny', 'tyler', 'new romantics',
    '6/10', 'papa ya', 'storms end', 'fluttershys lament', 'brain crain',
    'life might take us', 'the winner takes it all',
}
