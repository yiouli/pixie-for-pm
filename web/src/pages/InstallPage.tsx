export function InstallPage() {
  return (
    <main className="min-h-screen overflow-hidden bg-[radial-gradient(circle_at_top_left,rgba(15,118,110,0.2),transparent_28%),radial-gradient(circle_at_80%_20%,rgba(251,146,60,0.22),transparent_24%),linear-gradient(160deg,#f5efe1_0%,#e8f1ef_52%,#f6fbfa_100%)] px-4 py-8 text-stone-950 md:px-10 md:py-12">
      <div className="mx-auto flex max-w-6xl flex-col gap-8">
        <section className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="rounded-4xl border border-white/70 bg-white/82 p-8 shadow-[0_24px_90px_rgba(33,53,47,0.12)] backdrop-blur md:p-10">
            <p className="text-sm uppercase tracking-[0.35em] text-teal-700">
              Pixie PM
            </p>
            <h1 className="mt-4 max-w-3xl text-5xl font-bold leading-tight md:text-6xl">
              Install Pixie PM
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-stone-600">
              Add the bot to your Discord server, let Discord register the app
              commands, then open the settings flow from Discord with
              <span className="font-semibold text-stone-900"> /settings</span>.
            </p>

            <div className="mt-8 flex flex-col gap-4 sm:flex-row">
              <a
                className="inline-flex items-center justify-center rounded-full bg-teal-700 px-7 py-3 text-sm font-semibold text-white shadow-[0_14px_35px_rgba(15,118,110,0.28)] transition hover:bg-teal-600"
                href="/api/discord/install"
              >
                Install Pixie to Discord
              </a>
              <a
                className="inline-flex items-center justify-center rounded-full border border-stone-300 bg-white/75 px-7 py-3 text-sm font-semibold text-stone-800 transition hover:border-stone-400 hover:bg-white"
                href="/settings"
              >
                Open Settings URL
              </a>
            </div>

            <div className="mt-10 grid gap-4 md:grid-cols-3">
              <div className="rounded-3xl border border-teal-100 bg-teal-50/80 p-5">
                <div className="text-sm font-semibold uppercase tracking-[0.22em] text-teal-700">
                  1. Install
                </div>
                <p className="mt-3 text-sm leading-6 text-stone-700">
                  Use the Discord authorize screen to choose the server where
                  you want to install the bot.
                </p>
              </div>
              <div className="rounded-3xl border border-amber-100 bg-amber-50/85 p-5">
                <div className="text-sm font-semibold uppercase tracking-[0.22em] text-amber-700">
                  2. Run /settings
                </div>
                <p className="mt-3 text-sm leading-6 text-stone-700">
                  In Discord, run the slash command so Pixie can open the
                  server-scoped settings page with the right{" "}
                  <span className="font-semibold">server_id</span>.
                </p>
              </div>
              <div className="rounded-3xl border border-stone-200 bg-stone-50/90 p-5">
                <div className="text-sm font-semibold uppercase tracking-[0.22em] text-stone-600">
                  3. Verify E2E
                </div>
                <p className="mt-3 text-sm leading-6 text-stone-700">
                  Mention the bot or reply to one of its messages and confirm
                  the bot replies with the{" "}
                  <span className="font-semibold">PM_AGENT_OK</span> marker.
                </p>
              </div>
            </div>
          </div>

          <aside className="rounded-4xl border border-stone-900/5 bg-stone-950 p-8 text-stone-50 shadow-[0_24px_90px_rgba(20,20,20,0.18)] md:p-10">
            <div className="inline-flex rounded-full border border-white/15 bg-white/6 px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] text-stone-300">
              What This Install Grants
            </div>
            <ul className="mt-6 space-y-4 text-sm leading-7 text-stone-200">
              <li>
                View channels and read message history anywhere the bot is
                explicitly addressed.
              </li>
              <li>
                Send messages and thread replies so agent responses stay
                in-context.
              </li>
              <li>
                Create public threads for follow-up work from Discord
                conversations.
              </li>
              <li>
                Register slash commands through the same install flow using
                applications commands.
              </li>
            </ul>
            <div className="mt-8 rounded-3xl border border-white/10 bg-white/6 p-5 text-sm leading-7 text-stone-300">
              Pixie keeps the Discord trigger surface narrow: direct bot
              mention, reply-to-bot, or slash command. There is no
              channel-specific routing requirement.
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}
