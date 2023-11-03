import asyncio

from web3.auto import w3
from loguru import logger
from aiohttp import ClientSession
from aiohttp_proxy import ProxyConnector
from eth_account.messages import encode_defunct
from pyuseragents import random as random_useragent
from tenacity import retry, retry_if_exception, stop_after_attempt

logger.add("logger.log", format="{time:YYYY-MM-DD | HH:mm:ss.SSS} | {level} \t| {function}:{line} - {message}")


async def create_signature(nonce: str, private_key: str):
    message = encode_defunct(text=nonce)
    signed_message = w3.eth.account.sign_message(message, private_key)
    return signed_message.signature.hex()


async def sending_captcha(client: ClientSession):
    try:
        response = await client.get(f'http://rucaptcha.com/in.php?key={CAPTCHA_KEY}&method=turnstile'
                                    '&sitekey=0x4AAAAAAALBErj15WPJnECU&pageurl=https://www.earnalliance.com/')
        data = await response.text()
        if "ERROR_WRONG_USER_KEY" in data or "ERROR_ZERO_BALANCE" in data:
            logger.error(data)
            input()
            exit()
        elif 'ERROR' in data:
            logger.error(data)
            return await sending_captcha(client)
        return await solving_captcha(client, data[3:])
    except Exception as error:
        raise error


async def solving_captcha(client: ClientSession, id: str):
    while True:
        try:
            response = await client.get(f'http://rucaptcha.com/res.php?key={CAPTCHA_KEY}&action=get&id={id}')
            data = await response.text()
            if 'ERROR' in data:
                logger.error(data)
                return await sending_captcha(client)
            elif 'OK' in data:
                return data[3:]
        except Exception as error:
            raise error
        await asyncio.sleep(2)
    return await sending_captcha(client)


@retry(retry=retry_if_exception(Exception), stop=stop_after_attempt(5), reraise=True)
async def get_nonce(client: ClientSession, address: str) -> str:
    try:
        async with client.post('https://graphql-ea.earnalliance.com/v1/graphql',
                               json={
                                   "operationName": "GetSecurityChallenge",
                                   "variables": {
                                       "address": address.lower()
                                   },
                                   "query": "query GetSecurityChallenge($address: String!) {\n  payload: securityChallenge(address: $address) {\n    challenge\n    __typename\n  }\n}"
                               }) as response:
            nonce = (await response.json())['data']['payload']['challenge']
        return nonce
    except:
        raise Exception(f'{address} | Error getting nonce')


@retry(retry=retry_if_exception(Exception), stop=stop_after_attempt(5), reraise=True)
async def login(client: ClientSession, address: str, nonce: str, signature: str, captcha: str) -> str:
    try:
        async with client.post('https://graphql-ea.earnalliance.com/v1/graphql',
                               json={
                                   "operationName": "SignIn",
                                   "variables": {
                                       "address": address.lower(),
                                       "message": nonce,
                                       "signature": signature
                                   },
                                   "query": "mutation SignIn($address: String!, $message: String!, $signature: String!) {\n  payload: signIn(\n    args: {address: $address, message: $message, signature: $signature}\n  ) {\n    token\n    __typename\n  }\n}"
                               }, headers={'X-Turnstile-Token': captcha}) as response:
            token = (await response.json())['data']['payload']['token']
        return token
    except:
        raise Exception(f'{address} | Error login')


@retry(retry=retry_if_exception(Exception), stop=stop_after_attempt(5), reraise=True)
async def get_token(client: ClientSession, address: str, token: str) -> tuple:
    try:
        async with client.post('https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=AIzaSyD79OJpKaLDpdUO2UZrGNNU_14WyZPwB8w',
                               json={
                                   "token": token,
                                   "returnSecureToken": True
                               }) as response:
            authorization_token = (await response.json())['idToken']

        async with client.post('https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=AIzaSyD79OJpKaLDpdUO2UZrGNNU_14WyZPwB8w',
                               json={
                                   "idToken": authorization_token,
                               }) as response:
            user_id = (await response.json())['users'][0]['localId']
        return authorization_token, user_id
    except:
        raise Exception(f'{address} | Error getting token')


@retry(retry=retry_if_exception(Exception), stop=stop_after_attempt(5), reraise=True)
async def search_daily_chest(client: ClientSession, address: str) -> str:
    while True:
        try:
            async with client.post('https://graphql-ea.earnalliance.com/v1/graphql',
                                   json={
                                       "operationName": "SearchDailyChest",
                                       "variables": {
                                           "fetchCount": 0
                                       },
                                       "query": "mutation SearchDailyChest($fetchCount: Int!) {\n  payload: searchDailyChest(args: {fetchCount: $fetchCount}) {\n    status\n    rarity\n    totalSessionTime\n    sessionCount\n    totalFetchCount\n    __typename\n  }\n}"
                                   }) as response:
                status = (await response.json())['data']['payload']['status']

            if status == 'NOT_FOUND':
                continue

            return status
        except:
            raise Exception(f'{address} | Error searching daily chest')


@retry(retry=retry_if_exception(Exception), stop=stop_after_attempt(5), reraise=True)
async def open_daily_chest(client: ClientSession, address: str):
    try:
        async with client.post('https://graphql-ea.earnalliance.com/v1/graphql',
                               json={
                                   "operationName": "OpenDailyChest",
                                   "variables": {},
                                   "query": "mutation OpenDailyChest {\n  payload: openDailyChest {\n    rarity\n    rewards {\n    reward {\n    rewardRarity\n    rewardKey\n    rewardType\n    displayName\n    }\n    rewardValue\n    __typename\n  }\n  }\n}"
                               }) as response:
            (await response.json())['data']['payload']['rewards']
    except:
        raise Exception(f'{address} | Error opening daily chest')


@retry(retry=retry_if_exception(Exception), stop=stop_after_attempt(5), reraise=True)
async def get_balance(client: ClientSession, address: str, user_id: str):
    try:
        async with client.post('https://graphql-ea.earnalliance.com/v1/graphql',
                               json={
                                   "operationName": "getUser",
                                   "variables": {
                                       "id": user_id
                                   },
                                   "query": "fragment UserFields on Users {\n  bannerImgPath\n  bio\n  createdAt\n  discordId\n  id\n  power\n  supermintCredit\n  profilePicPath\n  twitterId\n  updatedAt\n  username\n  discord {\n    username\n    discriminator\n    __typename\n  }\n  twitter {\n    id\n    username\n    __typename\n  }\n  discriminator\n  allyToken\n  __typename\n}\n\nfragment UserWithWalletsFields on Users {\n  ...UserFields\n  wallets {\n    userId\n    address\n    createdAt\n    updatedAt\n    __typename\n  }\n  __typename\n}\n\nquery getUser($id: uuid!) {\n  payload: usersByPk(id: $id) {\n    ...UserWithWalletsFields\n    __typename\n  }\n}"
                               }) as response:
            token_balance = (await response.json())['data']['payload']['allyToken']

        with open('balances.txt', 'a', encoding='utf-8') as file:
            file.write(f'{token_balance}:{address}\n')

    except:
        raise Exception(f'{address} | Error getting balance')


async def worker(q_account: asyncio.Queue):
    while not q_account.empty():
        try:
            account = await q_account.get()
            address, private_key, ip, port, login_proxy, pass_proxy = account.split(':')
            proxy_url = ProxyConnector.from_url(f'http://{login_proxy}:{pass_proxy}@{ip}:{port}')
            async with ClientSession(
                connector=proxy_url,
                headers={
                    'origin': 'https://www.earnalliance.com',
                    'user-agent': random_useragent()
                }
            ) as client:

                logger.info(f'{address} | Getting nonce')
                nonce = await get_nonce(client, address)

                signature = await create_signature(nonce, private_key)

                logger.info(f'{address} | Sending captcha')
                captcha = await sending_captcha(client)

                logger.info(f'{address} | Login')
                token = await login(client, address, nonce, signature, captcha)

                logger.info(f'{address} | Getting token')
                authorization_token, user_id = await get_token(client, address, token)

                client.headers.update({'authorization': f'Bearer {authorization_token}'})

                logger.info(f'{address} | Searching Daily Chest')
                status = await search_daily_chest(client, address)

                if status == 'FOUND':
                    logger.info(f'{address} | Opening Daily Chest')
                    await open_daily_chest(client, address)
                    with open('successfully_claim_daily.txt', 'a', encoding='utf-8') as file:
                        file.write(f'{account}\n')
                elif status == 'OPENED':
                    logger.info(f'{address} | Daily Chest has been open')
                else:
                    logger.info(f'{address} | Daily Chest not found')

                logger.info(f'{address} | Getting token balance')
                await get_balance(client, address, user_id)

        except Exception as error:
            with open('error.txt', 'a', encoding='utf-8') as file:
                file.write(f'{account}\n')
            logger.error(error)

        else:
            logger.success('Successfully\n')

        finally:
            await asyncio.sleep(delay)


async def main():
    with open('accounts.txt') as f:
        accounts = f.read().splitlines()

    q_account = asyncio.Queue()
    for account in accounts:
        q_account.put_nowait(account)

    tasks = [asyncio.create_task(worker(q_account)) for _ in range(threads)]
    await asyncio.gather(*tasks)


if __name__ == '__main__':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    print("Bot Earn alliance @flamingoat\n")

    delay = int(input('Delay(sec): '))
    threads = int(input('Threads: '))

    CAPTCHA_KEY = 'CAPTCHA_KEY'

    asyncio.run(main())
    logger.debug('END')
    input("Press Enter to exit...")
    