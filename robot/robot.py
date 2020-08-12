import websockets
import json
import logging
import random
import asyncio
import ssl
import re
import multiset

MY_NAME_BASE = '🤖'
SERVER_URI = 'ws://localhost:9019'

# 0 - before join
# 1 - before ready
# 2 - ready
# 3 - game
# 4 - ob
STATE = 0

my_name = ''
my_cards = multiset.Multiset()
top_card = ''
my_id = -1
websocket = None

async def register():
    global my_name
    global my_id
    global STATE
    my_name = MY_NAME_BASE + str(random.randint(100, 999))
    await websocket.send(json.dumps({
        'action': 'register',
        'name': my_name
    }))
    result = await websocket.recv()
    data = json.loads(result)
    if data['type'] == 'register_result' and data['result'] == 'ok':
        my_id = data['id']
        STATE = 1
        return True
    else:
        return False

async def ready():
    global STATE
    await websocket.send(json.dumps({
        'action': 'ready',
        'name': my_name,
        'id': my_id,
    }))
    result = await websocket.recv()
    data = json.loads(result)
    if data['type'] == 'ready_result' and data['result'] == 'ok':
        STATE = 2

async def ob():
    global STATE
    await websocket.send(json.dumps({
        'action': 'ob',
        'id': my_id
    }))
    result = await websocket.recv()
    data = json.loads(result)
    if data['type'] == 'ready_result' and data['result'] == 'ob':
        STATE = 4

def is_compatible(card, top_card):
    if card[0] == 'W':
        return True
    if top_card[0] == 'W':
        return True
    return card[1] == top_card[1] or card[0] == top_card[0]

def same_number(card_a, card_b):
    if card_a[0] == 'W' or card_b[0] == 'W':
        return False
    return card_a[1] == card_b[1]

async def my_turn_start():
    random_delay = random.uniform(1, 2.5)
    await asyncio.sleep(random_delay)
    to_be_use = []
    for card in my_cards:
        if is_compatible(card, top_card):
            to_be_use.append(card)
            my_cards.remove(card, 1)
            break
    if len(to_be_use) == 0:
        await draw_a_card()
    else:
        for card in my_cards:
            if same_number(card, to_be_use[0]):
                to_be_use.append(card)
        for card in to_be_use[1:]:
            my_cards.remove(card, 1)
        await use_cards(to_be_use)
        if len(my_cards) == 1:
            await say_uno()
        elif len(my_cards) == 0:
            await win()

async def win():
    await websocket.send(json.dumps({
        'action': 'no_card',
        'id': my_id
    }))

async def exit_and_observe():
    pass

async def use_cards(cards):
    await websocket.send(json.dumps({
        'action': 'use_card',
        'id': my_id,
        'cards': cards
    }))

async def draw_a_card():
    await websocket.send(json.dumps({
        'action': 'draw_card',
        'id': my_id
    }))
    result = await websocket.recv()
    data = json.loads(result)
    if data['type'] == 'draw_result':
        my_cards.add(data['card'])

async def draw_cards_passive(cards):
    for card in cards:
        my_cards.add(card)

async def say_uno():
    await chat("UNO!!!")

async def chat(content):
    await websocket.send(json.dumps({
        'action': 'chat',
        'id': my_id,
        'content': content
    }))

async def update_top_card(card):
    global top_card
    top_card = card

async def start_working():
    global websocket
    websocket = await websockets.connect(SERVER_URI)
    ok = await register()
    if ok:
        await handle_messages()

async def game_start(card):
    global STATE
    STATE = 3
    await update_top_card(card)

async def game_end():
    global STATE
    STATE = 0

async def reset():
    global STATE
    global my_name
    global my_cards
    global my_id
    global top_card
    global websocket
    STATE = 0
    my_name = ''
    my_cards = multiset.Multiset()
    top_card = ''
    my_id = -1
    websocket = None

async def handle_chat(chat_content):
    chat_content = chat_content.strip()
    logging.info(chat_content)
    temp = re.search(r'(?<=^@robot\s).*', chat_content)
    if temp is None:
        return
    if temp[0] == 'ready':
        if STATE == 1:
            await ready()
    elif temp[0] == 'ob':
        if STATE == 1:
            await ob()
    else:
        await chat('啥玩意儿？能不能聊点👴听得懂的')

async def handle_messages():
    try:
        async for message in websocket:
            logging.info(f'get message from server: {message}')
            data = json.loads(message)
            if data['type'] == 'chat_noti':
                await handle_chat(data['content'])
            elif data['type'] == 'turn_start_noti':
                if data['player'] == my_name:
                    await my_turn_start()
            elif data['type'] == 'use_noti':
                await update_top_card(data['card'])
            elif data['type'] == 'game_start':
                await game_start(data['top_card'])
            elif data['type'] == 'draw_cards_result':
                await draw_cards_passive(data['cards'])
            elif data['type'] == 'game_end':
                await game_end()
                break
            elif data['type'] == 'init_cards':
                for card in data['cards']:
                    my_cards.add(card)
            else:
                message_type = data['type']
                logging.info(f'ignore message from server: {message_type}')  
    finally:
        await websocket.close()
        await reset()

logging.getLogger().setLevel(logging.INFO)
logging.info('Loading config.json')
with open('config.json') as config:
    data = json.loads(config.read())
    print(data)
    if 'base_name' in data.keys():
        MY_NAME_BASE = random.choice(data['base_name'])
    if 'uri' in data.keys():
        SERVER_URI = data['uri']
logging.info(f'Server uri: {SERVER_URI}')
logging.info('Start robot')
while True:
    asyncio.get_event_loop().run_until_complete(start_working())