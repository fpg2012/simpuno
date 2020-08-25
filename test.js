var socket
var name_text = document.getElementById("name-text");
var url_text = document.getElementById("url-text");
var join_button = document.getElementById("join-button");
var ready_button = document.getElementById("ready-button");
var ob_button = document.getElementById("ob-button")

var player_list = document.getElementById("user-list");

var card_list = document.getElementById("card-list");
var top_card_node = document.getElementById("top-card");

var now_player = document.getElementById("whose-turn");
var turn_number_node = document.getElementById("turn-number")

var use_button = document.getElementById("use-button");
var draw_button = document.getElementById("draw-button");

var choose_color_area = document.getElementById("choose-color");
var chosen_color_node = document.getElementById("chosen-color");

var say_button = document.getElementById("say-button")
var message_content_node = document.getElementById("message-content")

var log_list = document.getElementById("log-list");

var mute_checkbox = document.getElementById("mute-box")
var on_turn_tone = document.getElementById("on-turn-tone");

var log_example = log_list.children[0];
var selected_cards_in_order = []
var server_url = ""
var top_card = ""
var chosen_color = "R"

var convert_to_class = [];
convert_to_class["R"] = "red_card";
convert_to_class["G"] = "green_card";
convert_to_class["B"] = "blue_card";
convert_to_class["Y"] = "yellow_card";
convert_to_class["W"] = "wild_card";

url_text.value = "ws://localhost:9019"
use_button.onclick = use_cards;
draw_button.onclick = draw_a_card;
say_button.onclick = say_something;
init_color_radios();

// state 
// 0 - before register
// 1 - after register, before ready
// 2 - game started, other players' turn
// 3 - game started, my turn
// 4 - my turn, no card to use, after draw a card
// 9 - ob
var state = {
    value: 0,
    turn: 0
};

// unique id allocated by server 
var my_id = 0, my_name = "hello";
var cards;
var players = new Map();

class Player {
    constructor(name, state, card_quantity) {
        this.name = name;
        this.card_quantity = card_quantity;
        this.state = "waiting";

        this.html_node = document.createElement("li");
        this.html_node.setAttribute("id", "player-" + name)

        let player_name_node = document.createElement("span");
        player_name_node.setAttribute("class", "player-name");
        let player_name_node_t = document.createTextNode(name);
        player_name_node.appendChild(player_name_node_t);

        let player_state_node = document.createElement("span");
        player_state_node.setAttribute("class", "player-state");
        let player_state_node_t = document.createTextNode(state);
        player_state_node.appendChild(player_state_node_t);
        
        let player_card_quantity = document.createElement("span");
        player_card_quantity.setAttribute("class", "player-card-quantity");

        if(card_quantity == 0) {
            player_card_quantity.setAttribute("hidden", "");
        }

        this.html_node.appendChild(player_name_node);
        this.html_node.appendChild(player_state_node);
        this.html_node.appendChild(player_card_quantity);

        player_list.appendChild(this.html_node);
    }

    update() {
        // this.html_node.getElementsByClassName("player-name").innerText = state
        this.html_node.getElementsByClassName("player-state")[0].innerText = this.state;
        let card_q = this.html_node.getElementsByClassName("player-card-quantity")[0];
        if(card_q.hasAttribute("hidden") && (this.card_quantity > 0 || (this.state == "ready" && state.value >= 2 && state.value <= 4 || state.value == 9))) {
            card_q.removeAttribute("hidden");
        }
        card_q.innerText = this.card_quantity;
    }
}

join_button.onclick = function() {
    if(name_text.value.trim() == "") {
        alert("You should input a valid name!");
        return;
    }
    if(name_text.value.length > 20) {
        alert("Your name is too long!");
        return;
    }
    my_name = name_text.value.trim();
    if(url_text.value.trim() == "") {
        alert("You should input a valid server url!");
        return;
    }
    server_url = url_text.value.trim();
    socket = new WebSocket(server_url);
    socket.addEventListener("message", manage);
    socket.addEventListener("open", register)
}

ready_button.onclick = send_ready;
ob_button.onclick = send_ob;

document.onkeydown = function(e) {
    var e = e || window.event;
    switch(e.keyCode) {
        case 13:
            say_something();
        default:
            return;
    }
}

// handle the messages received from server
function manage(event) {
    data = JSON.parse(event.data);
    switch(data.type) {
        case "register_result":
            if(data.result == "ok") {
                my_id = data.id;
                console.log(my_id);
                register_ok();
                break;
            }
            else if(data.result == "name_used") {
                alert("Name has been used by other players. Choose another name.")
                break;
            }
        case "ready_result":
            if(data.result == "ok") {
                ready();
            }
            else if(data.result == "ob") {
                ready_ob();
            }
            break;
        case "game_start":
            game_start(data.top_card);
            break;
        case "player_state_change":
            update_player_list(data.name, data.to_state);
            break;
        case "init_players":
            init_players(data.players);
            break;
        case "use_noti":
            use_card_others(data.player, data.card);
            break;
        case "draw_noti":
            draw_card_others(data.player, data.num);
            break;
        case "draw_result":
            draw_card_result(data.card);
            break;
        case "draw_cards_result":
            draw_cards_result(data.cards);
            break;
        case "turn_start_noti":
            turn_start(data['player'], data['number']);
            if(data['player'] == my_name) {
                my_turn_start();
            }
            break;
        case "turn_end_noti":
            turn_end(data.player, data.turn);
            break;
        case "chat_noti":
            player_chat_info(data.player, data.content.trim());
            break;
        case "game_end":
            if(data.winner != '') {
                alert("Winner is " + data.winner);
                log_message("Winner is " + data.winner);
            }
            else {
                alert("Game aborted unexpectively.");
            }
            disable_everything();
            break;
        case "init_cards":
            init_cards = data.cards;
            update_card_list(init_cards);
            break;
        default:
            console.log("Unknow reply");
    }
}

function init_players(pls) {
    let len = pls.length;
    for(let i = 0;i < len;i++) {
        let temp = new Player(pls[i].name, pls[i].state, pls[i].card_q);
        players.set(pls[i].name, temp);
        temp.update();
    }
}

function disable_everything() {
    log_message("Please Reload!");
    let all_input = document.getElementsByTagName("input");
    for(let i = 0;i < all_input.length;i++) {
        all_input[i].disabled = true;
    }
}

// update state to ready
function ready() {
    state.value = 1;
    ready_button.disabled = true;
}

function ready_ob() {
    state.value = 9;
    document.getElementById("cards-area").setAttribute("hidden", "");
    ready_button.disabled = true;
}

// send ready request
function send_ready() {
    socket.send(JSON.stringify({
        "action": "ready",
        "id": my_id
    }));
}

// send ob request
function send_ob() {
    socket.send(JSON.stringify({
        "action": "ob",
        "id": my_id
    }));
}

// function update_player_list() {
//     player_list.innerHTML = "";
//     players.forEach(element => {
//         var temp_player_line = document.createElement("li");
//         var temp_player_name = document.createElement("span");
//         var temp_player_ready = document.createElement("b");
//         var temp_player_name_t = document.createTextNode(element.name + ",");
//         var ready_message = "waiting";
//         if(element.ready == "yes") {
//             ready_message = "READY";
//         }
//         else if(element.ready == "obs") {
//             ready_message = "Ob";
//         }
//         var temp_player_ready_t = document.createTextNode(ready_message);
//         temp_player_name.appendChild(temp_player_name_t)
//         temp_player_ready.appendChild(temp_player_ready_t);
//         temp_player_line.appendChild(temp_player_name);
//         temp_player_line.appendChild(temp_player_ready);
//         player_list.appendChild(temp_player_line);
//     });
//     if(Math.random() > 0.5) {
//         play_sound("join1");
//     }
//     else {
//         play_sound("join2");
//     }
// }

function update_player_list(player_name, to_state) {
    console.log(to_state);
    switch(to_state) {
        case "waiting":
            if(player_name == my_name) {
                return;
            }
            let cur_player = new Player(player_name, to_state, 0);
            players.set(player_name, cur_player);
            play_sound("join1");
            break;
        case "ready":
            temp = players.get(player_name);
            temp.state = to_state;
            temp.update();
            play_sound("join2");
            break;
        case "exit":
            temp_name = players.get(player_name).name;
            players.delete(temp_name);
            player_list.removeChild(document.getElementById("player-" + temp_name));
            break;
        case "ob":
            temp = players.get(player_name);
            temp.state = to_state;
            temp.update();
            break;
        default:
            console.log("Unknown State " + to_state);
    }
}

// judge if the card_a and card_b are compatible 
// compatible: same color, same pattern, or either of the two cards is wildcard
function is_card_comaptible(card_a, card_b) {
    return card_a[0] == card_b[0] || card_a[1] == card_b[1] || card_a[0] == "W" || card_b[0] == "W";
}

function update_card_list(cards_) {
    cards = cards_;
    cards.sort(function(a, b) {
        return a[1] - b[1];
    });
    card_list.innerHTML = "";
    cards.forEach(element => {
        var temp_card_line = document.createElement("li");
        var temp_card_line_t = document.createTextNode(element);
        var temp_checkbox = document.createElement("input");
        temp_checkbox.type = "checkbox";
        temp_card_line.appendChild(temp_checkbox);
        temp_card_line.appendChild(temp_card_line_t);
        temp_card_line.setAttribute("class", convert_to_class[element[0]]);
        temp_checkbox.onclick = function() {
            if(this.disabled == false) {
                var len = card_list.children.length;
                for(let i = 0;i < len;i++) {
                    if(card_list.children[i].children[0].checked == true) {
                        var selected_card = card_list.children[i].innerText;
                        break;
                    }
                }
                if(!selected_card) {
                    disable_uncompatible_cards();
                }
                else {
                    for(let i = 0;i < len;i++) {
                        let temp_card = card_list.children[i].innerText;
                        if(same_number(temp_card, selected_card)) {
                            card_list.children[i].children[0].disabled = false;
                        }
                        else {
                            card_list.children[i].children[0].disabled = true;
                        }
                    }
                }
                if(this.checked == true) {
                    selected_cards_in_order.push(this.parentNode.innerText);
                }
                else {
                    selected_cards_in_order.splice(selected_cards_in_order.indexOf(this.parentNode.innerText), 1);
                }
            }
        }
        card_list.appendChild(temp_card_line);
    })
    disable_uncompatible_cards();
}

function disable_uncompatible_cards() {
    // console.log("test");
    let len = card_list.children.length;
    console.log(len);
    for(let i = 0;i < len;i++) {
        let element = card_list.children[i];
        if(is_card_comaptible(element.innerText, top_card)) {
            element.children[0].checked = false;
            element.children[0].disabled = false;
            // console.log("not disable " + element.innerText);
        }
        else {
            element.children[0].checked = false;
            element.children[0].disabled = true;
            // console.log("disable " + element.innerText);
        }
    }
}

function same_number(card_a, card_b) {
    if(card_a[0] != "W" && card_b[0] != "W") {
        return card_a[1] == card_b[1];
    }
    else if(card_a[0] == "W" && card_b[0] == "W") {
        return card_a[1] == card_b[1];
    }
    return false;
}

function update_top_card() {
    top_card_node.innerHTML = top_card;
    top_card_node.setAttribute("class", convert_to_class[top_card[0]]);
    console.log(top_card);
    disable_uncompatible_cards();
}

// connect to the server, and get a unique id
function register() {
    // my_name += Math.floor(Math.random() * 1000).toString()
    console.log(my_name);
    socket.send(
        JSON.stringify({
            "action": "register",
            "name": my_name
        })
    )
    state.value = 1
}

function register_ok() {
    join_button.disabled = true;
    ready_button.disabled = false;
    ob_button.disabled = false;
    log_message("Successfully Registered.");
}

function game_start(top_card_) {
    state.value = 2;
    top_card = top_card_;
    update_top_card();
    document.getElementById("server-area").style.display = "none";
    players.forEach(player => {
        player.card_quantity = 7;
        player.update();
    })
}

function turn_start(player_name, turn_number) {
    state.value = 3;
    now_player.innerText = player_name;
    state.turn = turn_number;
    turn_number_node.innerText = turn_number;
}

function my_turn_start() {
    state.value = 3
    use_button.disabled = false;
    draw_button.disabled = false;
    selected_cards_in_order.length = 0;
    play_sound("on-turn-tone");
}

function turn_end(player_name, turn_number) {
    state.turn = turn_number;
    turn_number_node.innerText = turn_number;
    now_player.innerText = player_name;
    if(player_name == my_name) {
        my_turn_end();
    }
}

function my_turn_end() {
    state.value = 2;
    use_button.disabled = true;
    draw_button.disabled = true;
}

function draw_a_card() {
    socket.send(JSON.stringify({
        "action": "draw_card",
        "id": my_id,
    }));
}

function draw_cards_result(cards_) {
    for(let i = 0;i < cards_.length;i++) {
        cards.push(cards_[i]);
    }
    update_card_list(cards);
}

function draw_card_result(card) {
    cards.push(card);
    update_card_list(cards);
}

function draw_card_others(player_name, num) {
    log_message(
        player_name + " draw " + num.toString() + " card(s)");
    let temp_player = players.get(player_name);
    temp_player.card_quantity += num;
    temp_player.update();
}

function use_cards() {
    if(selected_cards_in_order.length == 0) {
        alert("Select at least a card!");
        return;
    }
    socket.send(JSON.stringify({
        "action": "use_card",
        "id": my_id,
        "cards": selected_cards_in_order
    }));
}

function use_card_others(player_name, card) {
    if(player_name == my_name) {
        for(let i = 0;i < selected_cards_in_order.length;i++) {
            let temp = cards.indexOf(selected_cards_in_order[i]);
            cards.splice(temp, 1);
        }
        update_card_list(cards);
        selected_cards_in_order.length = 0;
    }

    let temp_player = players.get(player_name);
    temp_player.card_quantity -= 1;
    temp_player.update();

    top_card = card;
    update_top_card();
    use_card_message(player_name, card);
}

function log_message(message) {
    let new_log_line = document.createElement("li");
    let new_log_line_t = document.createTextNode(message);
    new_log_line.appendChild(new_log_line_t);
    log_list.insertBefore(new_log_line, log_list.children[0]);
}

function use_card_message(player_name, card) {
    let new_log_line = document.createElement("li");
    let new_log_line_c = document.createElement("span");
    let new_log_line_t = document.createTextNode(player_name + " uses ");
    new_log_line_c.setAttribute("class", convert_to_class[card[0]]);
    new_log_line_c.innerText = card;
    new_log_line.appendChild(new_log_line_t);
    new_log_line.append(new_log_line_c);
    log_list.insertBefore(new_log_line, log_list.children[0]);
}

function player_chat_info(player_name, message) {
    let new_log_line = document.createElement("li");
    let new_log_line_t = document.createTextNode(player_name + ": " + message);
    new_log_line.appendChild(new_log_line_t);
    new_log_line.setAttribute("class", "chat-message")
    log_list.insertBefore(new_log_line, log_list.children[0]);
    if(player_name != my_name) {
        play_sound("chat-sound");
    }
}

function say_something() {
    message_content_node.value = message_content_node.value.trim();
    if(message_content_node.value == '') {
        alert("Message cannot be empty!");
        return;
    }
    socket.send(JSON.stringify({
        "action": "chat",
        "id": my_id,
        "content": message_content_node.value
    }));
    message_content_node.value = ''
    return false;
}

function init_color_radios() {
    let radios = choose_color_area.getElementsByTagName("input");
    for(let i = 0;i < radios.length;i++) {
        radios[i].onclick = function() {
            let radios = choose_color_area.getElementsByTagName("input");
            for(let i = 0;i < radios.length;i++) {
                if(radios[i] != this) {
                    radios[i].checked = false;
                }
            }
            chosen_color_node.innerText = this.id[0];
        }
    }
}

function play_sound(sound) {
    let temp = document.getElementById(sound);
    if(!mute_checkbox.checked) {
        temp.play();
    }
}