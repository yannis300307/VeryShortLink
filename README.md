# Very ShortLink

Very Short Link if one of the simplest self hosted url shortener. Simply put your url in the middle input bar, click on the button and you get your shortened url immediately!

## Installation

Clone the repository with `git clone https://github.com/yannis300307/VeryShortLink.git`.

Edit the compose file `docker-compose.yml` and edit the environment variables:
 - `EXPIRATION_DELAY`: Delay (in seconds) before a link became inactive.
 - `MAX_LINK_AMOUNT`: The maximum amount of links that can be stored at the same time in the database. It prevents potential spam bots to fill up completly the hard drive.
 - `WEBSITE_URL`: The base URL of the website.
 - `FORBIDDEN_WEBSITES_LIST_PROVIDER`: A forbidden websites list provider because we don't want to link to bad websites. Must link to a valid JSON (Edit the JSON parsing code if yours if different). The default one is kind of sufficient.
 - `MAX_LINK_PER_HOUR`: The maximum number of links that a single ip can create in one hour.
 - `BAN_TIME`: How long is banned the user if it excceded rate limit.

All variables have default values that are set in `main.py` but you should change the `WEBSITE_URL` variable to your own URL.
You can change the database folder by editing the volume path.

## Current features:
 - Short a link
 - Customize all the settings
 - Cloudflare Tunnels friendly

## Planned features:
 - Moderator pannel
 - Custom Ids
