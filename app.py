from flask import Flask, request, jsonify, render_template_string
import requests

app = Flask(__name__)

def get_btc_balance_and_last_tx(address):
    try:
        url = f'https://blockstream.info/api/address/{address}'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        balance_sats = data['chain_stats']['funded_txo_sum'] - data['chain_stats']['spent_txo_sum']
        balance_btc = balance_sats / 1e8

        tx_url = f'https://blockstream.info/api/address/{address}/txs'
        tx_response = requests.get(tx_url)
        tx_response.raise_for_status()
        tx_data = tx_response.json()

        if not tx_data:
            return balance_btc, None, None, None

        last_received_tx = None
        for tx in tx_data:
            for vout in tx['vout']:
                if address in vout['scriptpubkey_address']:
                    last_received_tx = tx
                    break
            if last_received_tx:
                break

        if last_received_tx:
            txid = last_received_tx['txid']
            senders = [vin.get('prevout', {}).get('scriptpubkey_address', 'Unknown') for vin in last_received_tx['vin']]
            amount_received_sats = sum(vout['value'] for vout in last_received_tx['vout'] if vout['scriptpubkey_address'] == address)
            amount_received_btc = amount_received_sats / 1e8
        else:
            txid = None
            senders = []
            amount_received_btc = 0

        return balance_btc, txid, senders, amount_received_btc

    except requests.exceptions.RequestException as e:
        return None, None, None, None

def get_confirmations(txid):
    if not txid:
        return 0

    try:
        status_url = f'https://blockstream.info/api/tx/{txid}/status'
        status_response = requests.get(status_url)
        status_response.raise_for_status()
        status_data = status_response.json()

        current_height_response = requests.get('https://blockstream.info/api/blocks/tip/height')
        current_height_response.raise_for_status()
        current_height = int(current_height_response.text)

        block_height = status_data.get('block_height')
        if status_data.get('confirmed') and block_height:
            confirmations = current_height - block_height + 1
        else:
            confirmations = 0

        return confirmations
    except requests.exceptions.RequestException:
        return 0

def get_btc_usd_price():
    try:
        price_response = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd')
        price_response.raise_for_status()
        price_data = price_response.json()
        btc_usd = price_data['bitcoin']['usd']
        return btc_usd
    except requests.exceptions.RequestException:
        return None

@app.route('/')
def home():
    with open('index.html') as file:
        return render_template_string(file.read())

@app.route('/balance', methods=['GET'])
def balance():
    address = request.args.get('address')
    if not address:
        return jsonify({'error': 'Bitcoin address is required'}), 400

    balance_btc, txid, senders, amount_received = get_btc_balance_and_last_tx(address)
    confirmations = get_confirmations(txid) if txid else 0
    btc_usd = get_btc_usd_price()

    if btc_usd is not None:
        balance_usd = balance_btc * btc_usd
        amount_received_usd = (amount_received * btc_usd) if amount_received else 0
    else:
        balance_usd = amount_received_usd = "N/A"

    data = {
        'address': address,
        'balance_btc': balance_btc,
        'balance_usd': f"${balance_usd:,.2f} USD" if isinstance(balance_usd, (int, float)) else balance_usd,
        'last_transaction': {
            'txid': txid,
            'senders': senders,
            'amount_received_btc': amount_received,
            'amount_received_usd': f"${amount_received_usd:,.2f} USD" if isinstance(amount_received_usd, (int, float)) else amount_received_usd,
            'confirmations': confirmations
        } if txid else "No transactions found"
    }

    return jsonify(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
