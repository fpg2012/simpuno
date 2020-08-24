import random
import json
import websockets
import logging
import asyncio
import ssl

PLAYERS = {}
READY_PLAYERS = set()
OB_PLAYERS = set()
player_order = []
DECK = []
SERVER_ADDR = '0.0.0.0'
SERVER_PORT = '9019'
top_card = ''
SSL = False
CERT_FILE = None
KEY_FILE = None

COLORS = ['R', 'G', 'B', 'Y', 'W']
CONTENTS = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'X', 'R', 'A']

# state value
# 0 - before start
# 1 - game started
STATE = {
    'value': 0,
    'turn': None,
}

class Player:
    
    def __init__(self, id, name, websocket):
        self.id = id
        self.name = name
        self.websocket = websocket

class Turn:

    def __init__(self, num, cycle, add_direction=True):
        self.base_num = num
        self.real_num = num
        self.next_num = num
        self.cycle = cycle
        self.add_direction = add_direction
    
    def update(self):
        logging.info(f'{self.base_num} -> {self.next_num}')
        self.base_num = self.next_num
        self.real_num += 1

    def add(self, step=1, skip_current=False):
        self.next_num = (step + self.next_num) % self.cycle
        if skip_current and self.next_num == self.base_num:
            self.add(1)

    def sub(self, step=1, skip_current=False):
        self.next_num = (self.next_num - step) % self.cycle
        if skip_current and self.next_num == self.base_num:
            self.sub(1)

    def after_add(self, step=1, skip_current=False, temp=None):
        if temp is None:
            temp = self.next_num
        temp = (step + temp) % self.cycle
        if skip_current and temp == self.base_num:
            temp = self.after_add(1, temp=temp)
        return temp
    
    def after_sub(self, step=1, skip_current=False, temp=None):
        if temp is None:
            temp = self.next_num
        temp = (temp - step) % self.cycle
        if skip_current and temp == self.base_num:
            temp = self.after_add(1, temp=temp)
        return temp
        
    def after_advance(self, step=1, skip_current=False):
        if self.add_direction:
            return self.after_add(step, skip_current)
        else:
            return self.after_sub(step, skip_current)

    def advance(self, step=1, skip_current=False):
        logging.info(f'advance! now {self.next_num}')
        if self.add_direction:
            self.add(step, skip_current)
        else:
            self.sub(step, skip_current)
        logging.info(f'next num {self.next_num}')

# generate the standard deck
def init_deck():
    global top_card
    for color in COLORS[:4]:
        for content in CONTENTS:
            card = color + content
            for _ in range(4):
                DECK.append(card)
    for _ in range(2):
        DECK.append('W0')
        DECK.append('W1')
    random.shuffle(DECK)
    top_card = DECK[0]

def init_player_order():
    global player_order
    player_order = list(READY_PLAYERS)
    random.shuffle(player_order)

async def init_draw_cards():
    cards = []
    for player in player_order:
        cards.clear()
        for _ in range(7):
            top = await get_top()
            cards.append(top)
        message = json.dumps({
            "type": "init_cards",
            "cards": cards
        })
        await PLAYERS[player].websocket.send(message)

def get_current_player():
    return player_order[STATE['turn'].base_num]

def get_next_player():
    return player_order[STATE['turn'].after_advance(1)]

def is_synced(player_id):
    return player_id == get_current_player()

def is_compatible(card, top_card):
    if card[0] == 'W':
        return True
    if top_card[0] == 'W':
        return True
    return card[1] == top_card[1] or card[0] == top_card[0]

# get the top of the deck
async def get_top():
    return DECK.pop()

async def dispose(card):
    DECK.insert(0, card)

async def register(name, websocket, ob=False):
    if name in [pl.name for _, pl in PLAYERS.items()]:
        await websocket.send(json.dumps({
        'type': 'register_result',
        'result': 'name_used'
        }))
        return
    player_id = random.randint(10000, 100000)
    while player_id in PLAYERS.keys():
        player_id = random.randint(10000, 100000)
    logging.info(f"{name} join, id {player_id}")
    player = Player(player_id, name, websocket)
    PLAYERS[player_id] = player
    await websocket.send(json.dumps({
        'type': 'register_result',
        'result': 'ok',
        'id': player_id
        }))
    await notify_users()
    if ob:
        await player_ready(player_id, ob=True)

async def unregister(websocket):
    if len(PLAYERS) == 0:
        return
    k = 0
    for id, pl in PLAYERS.items():
        if pl.websocket == websocket:
            k = id
            break
    PLAYERS.pop(k)
    if id in READY_PLAYERS:
        READY_PLAYERS.remove(k)
    elif id in OB_PLAYERS:
        OB_PLAYERS.remove(k)
    await notify_users()

async def player_ready(player_id, ob=False):
    if not ob:
        READY_PLAYERS.add(player_id)
    else:
        OB_PLAYERS.add(player_id)
    websocket = PLAYERS[player_id].websocket
    result = 'ok'
    if ob:
        result = 'ob'
    await websocket.send(json.dumps({
        'type': 'ready_result', 
        'result': result
        }))
    await notify_users()
    if STATE['value'] == 0 and len(READY_PLAYERS) == len(PLAYERS) - len(OB_PLAYERS) and len(READY_PLAYERS) > 1:
        await start_game()

async def start_game():
    init_deck()
    init_player_order()
    await notify_game_start()
    STATE['value'] = 1
    STATE['turn'] = Turn(0, len(player_order))
    await init_draw_cards()
    await start_turn()

async def start_turn():
    await notify_turn_start(
        get_current_player(), 
        STATE['turn'].real_num
        )

async def end_turn(player_id):
    await notify_turn_end(player_id, STATE['turn'].real_num)
    STATE['turn'].advance()
    STATE['turn'].update()

async def notify_game_start():
    message = json.dumps({
        'type': 'game_start',
        'top_card': top_card
        })
    await asyncio.wait([pl.websocket.send(message) for _, pl in PLAYERS.items()])

async def notify_users():
    player_list = []
    for id, pl in PLAYERS.items():
        ready = 'no'
        if id in READY_PLAYERS:
            ready = 'yes'
        elif id in OB_PLAYERS:
            ready = 'obs'
        player_list.append({'name': pl.name, 'ready': ready})
    message = json.dumps({'type': 'user_noti', 'players': player_list})
    await asyncio.wait([pl.websocket.send(message) for _, pl in PLAYERS.items()])

async def notify_draw_card(player_id, num):
    message = json.dumps({
        'type': 'draw_noti', 
        'player': PLAYERS[player_id].name,
        'num': num
        })
    await asyncio.wait([pl.websocket.send(message) for _, pl in PLAYERS.items()])

async def draw_card(player_id, should_synced=True):
    if should_synced and not is_synced(player_id):
        return
    card = await get_top()
    message = json.dumps({
        'type': 'draw_result',
        'card': card
    })
    await PLAYERS[player_id].websocket.send(message)
    await notify_draw_card(player_id, 1)

async def draw_cards(player_id, num, should_synced=True):
    if should_synced and not is_synced(player_id):
        return
    logging.info(f'draw {num} cards')
    cards = []
    for _ in range(num):
        cards.append(await get_top())
    message = json.dumps({
        'type': 'draw_cards_result',
        'cards': cards
    })
    await PLAYERS[player_id].websocket.send(message)
    await notify_draw_card(player_id, num)

async def use_cards(player_id, cards):
    for card in cards:
        logging.info(card)
        await use_card(player_id, card)

def get_card_type(card):
    if card[0] == 'W':
        return card
    elif '0' <= card[1] <= '9':
        return 'N'
    return card[1]

async def use_card(player_id, card):
    global top_card
    if not is_synced(player_id):
        logging.error(f'Game seem not synced. Someone try to use a card outside its turn.')
        return
    if not is_compatible(card, top_card):
        logging.error(f'Incompatible card {card}! top card: {top_card}')
        return
    top_card = card
    card_type = get_card_type(card)
    to_run = None
    if card_type == 'X':
        STATE['turn'].advance(skip_current=True)
    elif card_type == 'R':
        STATE['turn'].add_direction = not STATE['turn'].add_direction
    elif card_type == 'A':
        logging.info(PLAYERS[get_next_player()].name)
        to_run = draw_cards(get_next_player(), 2, should_synced=False)
    elif card_type == 'W0':
        pass
    elif card_type == 'W1':
        to_run = draw_cards(get_next_player(), 4, should_synced=False)
    await dispose(card)
    await notify_use_card(player_id, card)
    if to_run is not None:
        await to_run

async def notify_use_card(player_id, card):
    message = json.dumps({
        'type': 'use_noti', 
        'player': PLAYERS[player_id].name, 
        'card': card
        })
    await asyncio.wait([pl.websocket.send(message) for _, pl in PLAYERS.items()])

async def notify_turn_start(player_id, turn_number):
    message = json.dumps({
        'type': 'turn_start_noti', 
        'player': PLAYERS[player_id].name, 
        'number': turn_number
        })
    await asyncio.wait([pl.websocket.send(message) for _, pl in PLAYERS.items()])

async def notify_turn_end(player_id, turn_number):
    message = json.dumps({
        'type': 'turn_end_noti',
        'player': PLAYERS[player_id].name,
        'number': turn_number
        })
    await asyncio.wait([pl.websocket.send(message) for _, pl in PLAYERS.items()])

async def game_end(player_id):
    await notify_game_end(player_id)
    await notify_game_end(player_id)
    PLAYERS.clear()
    READY_PLAYERS.clear()
    DECK.clear()
    OB_PLAYERS.clear()
    STATE['value'] = 0
    STATE['turn'] = None

async def notify_game_end(player_id):
    winner_name = ''
    if player_id != 0:
        winner_name = PLAYERS[player_id].name
    message = json.dumps({
        'type': 'game_end', 
        'winner': winner_name
        })
    await asyncio.wait([pl.websocket.send(message) for _, pl in PLAYERS.items()])

async def notify_server_close():
    message = json.dumps({
        'type': 'server_close',
        })
    await asyncio.wait([pl.websocket.send(message) for _, pl in PLAYERS.items()])

async def notify_player_chat(player_id, message):
    message = json.dumps({
        'type': 'chat_noti',
        'player': PLAYERS[player_id].name,
        'content': message
        })
    await asyncio.wait([pl.websocket.send(message) for _, pl in PLAYERS.items()])

async def start_server(websocket, path):
    try:
        async for message in websocket:
            data = json.loads(message)
            if data['action'] == 'chat':
                await notify_player_chat(data['id'], data['content'])
            elif data['action'] == 'ob':
                await player_ready(data['id'], ob=True)
            elif STATE['value'] == 0:
                if data['action'] == 'register':
                    await register(data['name'], websocket)
                elif data['action'] == 'ready':
                    await player_ready(data['id'])
                else:
                    logging.error('Unknow action')
            elif STATE['value'] == 1:
                if data['action'] == 'use_card':
                    await use_cards(data['id'], data['cards'])
                    await end_turn(data['id'])
                    await start_turn()
                elif data['action'] == 'draw_card':
                    await draw_card(data['id'])
                    await end_turn(data['id'])
                    await start_turn()
                elif data['action'] == 'no_card':
                    await game_end(data['id'])
                elif data['action'] == 'register':
                    await register(data['name'], websocket, True)
                else:
                    logging.error('Unknow action')
    finally:
        player_id = 0
        for _, player in PLAYERS.items():
            if player.websocket == websocket:
                player_id = player.id
                break
        if player_id != 0:
            logging.error(f'{PLAYERS[player_id].name} exit.')
        if player_id in player_order:
            if STATE['value'] == 1:
                await game_end(0)
        await unregister(websocket)

logging.getLogger().setLevel(logging.INFO)
logging.info('Load config')
with open('config.json') as config:
    data = json.loads(config.read())
    if 'ssl' in data.keys() and data['ssl'] == 'yes':
        SSL = True
        CERT_FILE = data['cert']
        KEY_FILE = data['key']
    if 'addr' in data.keys():
        SERVER_ADDR = data['addr']
    if 'port' in data.keys():
        SERVER_PORT = data['port']
logging.info(f'url {SERVER_ADDR}:{SERVER_PORT}')
logging.info('Server start')
if SSL:
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(CERT_FILE, KEY_FILE)
    start = websockets.serve(start_server, SERVER_ADDR, SERVER_PORT, ssl=ssl_context)
else:
    start = websockets.serve(start_server, SERVER_ADDR, SERVER_PORT)
asyncio.get_event_loop().run_until_complete(start)
asyncio.get_event_loop().run_forever()