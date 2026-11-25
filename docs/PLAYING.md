# How to play Chowder: Bookin' Cook (notes for Claude Code sessions)

This file tells a future Claude Code session how to play the game with the
Playwright MCP tools. The user wants Claude to play the game directly: look
at a screenshot, decide, click. Do not write a bot that reads game state.

## Set up

1. Start the server: `powershell -NoProfile -ExecutionPolicy Bypass -File serve.ps1 -NoBrowser`
   (run it in the background).
2. Mute the page audio before it loads. The game is very loud.
   Use `browser_run_code_unsafe`:
   ```js
   async (page) => {
     await page.addInitScript(() => {
       const AC = window.AudioContext;
       window.AudioContext = class extends AC {
         constructor(o) { super(o); this.suspend(); }
         resume() { return Promise.resolve(); }
       };
       window.webkitAudioContext = window.AudioContext;
     });
     await page.goto('http://localhost:8642/');
   }
   ```
   Also click the in-game speaker icon (190, 792) once a level starts.
   It is a toggle. Check the icon in the next screenshot.
3. Wait about 7 s for loading. Click (905, 745) for "Play" on the title,
   then (905, 745) again on the next screens ("Play" / "Skip").

## Screenshots

- Do one action batch and one screenshot in the same `browser_run_code_unsafe`
  call. Save to `f:/workspace/chowder-bookin-cook/.playwright-mcp/<name>.png`
  (only paths in the project are allowed), then read the file.
- A round trip (run + read) takes a few seconds of real time. The game
  timer keeps running. So queue many clicks in one call.
- Short waits (about 1 s) after the last click are enough for a screenshot.
- `browser_take_screenshot` sometimes times out. `page.screenshot()` inside
  `browser_run_code_unsafe` is more reliable.
- The .playwright-mcp folder is in .gitignore. Delete it when you finish.

## Coordinates (viewport about 1066 x 936, game letterboxed)

| Thing                         | Click         |
|-------------------------------|---------------|
| Fridge: cheese                | (80, 165)     |
| Fridge: apple                 | (185, 160)    |
| Fridge: leek                  | (75, 265)     |
| Fridge: mushroom              | (185, 262)    |
| Counter (Schnitzel's output)  | (207, 462)    |
| Pink sauce machine (input)    | (385, 225)    |
| Blue sauce machine (input)    | (528, 225)    |
| Orange sauce machine (input)  | (672, 235)    |
| Pink machine output (pick up) | (380, 262)    |
| Blue machine output           | (525, 262)    |
| Orange machine output         | (668, 275)    |
| Cupcake stand (level 2+)      | (790, 215)    |
| Trash can                     | (140, 680)    |
| Customer seat 1 / 2 / 3       | (320, 760) / (470, 760) / (612, 760) |
| Cash on counter, seat 1 / 2   | (322, 672) / (465, 672) |
| Next / Play / Continue button | (905, 745)    |
| No-fruits bonus reels         | (255, 530), (535, 530), (815, 530) |

## Rules (learned)

- Click a waiting customer to give a menu. About 1-2 s later the order
  bubble shows the dish: a base (cheese, apple, leek, mushroom) and maybe a
  sauce colour on top (pink, blue, orange). No sauce colour = plain.
  Light cyan on a mushroom = blue sauce.
- Click the fridge item: Schnitzel makes it and puts it on the counter.
- Pick it up from the counter, take it to the right sauce machine if the
  order has sauce, pick it up from the machine, click the customer.
- Then click the cash on the counter in front of that seat.
- When the timer shows CLOSED, no new customers come, but serve the ones
  that are still there. Their money still counts.
- Customers slide left when a seat frees up. Check which seat has which
  order before you serve. Clicking the order bubble also works.
- Wrong items block the counter. Throw them in the trash.
- Cupcake (level 2+): click the stand, then a customer. It fills their
  patience bar to full. Use it on a customer whose bar is red.
- Level end: "No-fruits bonus" slot machine. Click each reel when it shows a
  non-fruit (cheese, mushroom, leek). Clicking all three at once worked.
  Bonus +100. Happy customers give +50 each.

## Timing

- Fridge prep: about 5 s. Clicking the counter before the item is there
  is lost (Chowder walks there and does nothing). Use 5000 ms.
- Sauce machine: about 4 s. Wait 4300 ms before the machine pickup click.
- A walk across the room: about 1 s.
- Clicks are queued (a green check shows). Chowder does them in order.
  Queue a full chain: counter -> machine -> (wait) -> machine output -> seat -> cash.
- Prefire: as soon as the counter is free, order the next fridge item.
  Then it prepares while Chowder walks to machines and customers.
  Do not order a second item while one is still on the counter.
- Give menus to new customers while food is prepping.
- Level 1 goal: 400 dollops in about 95 s. Level 2: 500 dollops.
  A dish pays about 80-100 dollops, so you need 5-6 dishes per level.

## Example batch (apple with pink sauce, customer at seat 1)

```js
async (page) => {
  const c = (x, y) => page.mouse.click(x, y, { delay: 50 });
  const w = t => page.waitForTimeout(t);
  await c(185, 160); await w(5000);                // apple
  await c(207, 462); await w(150); await c(385, 225); // counter -> pink machine
  await w(1200); await c(80, 165);                 // prefire next item
  await w(3000); await c(380, 262); await w(150);  // pick up from machine
  await c(320, 760); await w(150); await c(322, 672); // serve + cash
  await w(1000);
  await page.screenshot({ path: 'f:/workspace/chowder-bookin-cook/.playwright-mcp/s.png' });
}
```

## Results so far

- Level 1: cleared on the 3rd try (471 dollops + bonus, total 661).
- Level 2: 1st try about 450 (missed 500). Main time losses: clicking the
  counter or machine too early, and a stray item that blocked the counter.
