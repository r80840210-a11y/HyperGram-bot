# HyperGram Registration Bot — demo

A Telegram bot prototype with:
- `/start` welcome screen
- Russian (+7) and US (+1) demo number selection
- unique allocation from a finite fictional test pool
- “My numbers” history
- locally generated demo codes for UI testing

**Important:** all numbers are fictional sandbox placeholders. This bot does not receive real SMS, forward Telegram login codes, or provide numbers for creating accounts on third-party services.

## 1. Create the Telegram bot
1. Open `@BotFather` in Telegram.
2. Run `/newbot`, choose a name and username.
3. Copy the token.

## 2. Upload to GitHub
1. Create a new GitHub repository, e.g. `hypergram-registration-demo`.
2. Upload all files from this folder (not the ZIP itself).
3. Commit the files.

## 3. Deploy on Render
1. Sign in to Render and choose **New + → Blueprint**.
2. Connect the GitHub repository.
3. Render detects `render.yaml`.
4. In the service's Environment settings, add `BOT_TOKEN` with the token from BotFather.
5. Deploy. The service should start with `python bot.py`.

## Notes
- This demo uses SQLite. On Render, the local filesystem may be ephemeral unless a persistent disk is configured. For durable production data, use Render PostgreSQL and migrate the database layer.
- Do not commit your bot token to GitHub.
- A real production number/SMS integration requires a provider that explicitly supports your own service's verification workflow and authorized numbers. Keep verification codes within that service; do not relay third-party account login codes.
