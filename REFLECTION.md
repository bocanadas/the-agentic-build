# Reflection

## 1. How far did the agent get?

Really far. I'm very impressed with what the agent came up with. This is definitely something that looks nice on a portfolio and that is genuinely useful.

**Did it fully implement your spec?**

Yes, I fully implemented my SPEC.md.

**What percentage of your acceptance criteria passed on the first try?**

It passed 100% of my acceptance criteria on the first try. It had the quiz logic, user login, and the UX was very clean (it even added color to the CLI). However, security was the most lacking area.

## 2. Where did you intervene?

I never intervened with the agent until it stopped working. The agent thought for 546s and worked for a total time of 13 min 8s. I only intervened in Phase 3 once I saw the problems the review agent found.

## 3. How useful was the AI review?

Very helpful. The review agent was able to find issues with my raw agent output code in all sectors. It identified problems related to Security & Git Hygiene, Bugs & Logic Errors, Code Quality, and UX Issues. The most important sector being security.

**Did it catch real bugs?**

Yes, it caught real bugs like getting stuck in the login and create account screen. There was no real way to get back to the main menu without having to terminate the application with `Control + C`. It also caught another bug where the user would get kicked out to the main screen if their password was wrong instead of prompting the user to try again.

**Did it miss anything important?**

The only thing I visually tested and saw that it missed was the weird placement of "Confirm Password" in the UI for creating an account. Depending on the person, it could be considered a bug.

**Did it flag things that weren't actually problems?**

It didn't flag anything insignificant as `FAILED`. However, some of the `WARN`s seemed a bit out of scope for a small project. For instance, the review agent told me to atomically swap in variables so that we aren't writing directly to the `.json` files. This seemed a bit overkill to me.

## 4. Spec quality → output quality

**In hindsight, what would you change about your spec to get a better result from the agent?**

I would've been more adamant about security since the build agent didn't even make a `.gitignore` file to hide the database, scores, and user information. The build agent also used SHA256 for password encryption which could be brute forced. This made me think that I should be more specific about what encryption should look like for the application because, if not specified, the agent will just pick something simple.

## 5. When would you use this workflow?

I would use this workflow when working on something that I need to make quickly and I know with some certainty that it isn't completely slop code and it is somewhat robust. However, it felt like it took me a bit longer than I anticipated but that might just be because I was looking at best practices for creating a SPEC file and one shotting apps with Cursor.

**Based on this experience, when do you think plan-delegate-review is better than conversational back-and-forth?**

I think it's better when you need to ship something somewhat robust in the next 24-48 Hours. I enjoyed this workflow because it was less manual work or reading code. It also seems to be better if you're trying to be more efficient in your token usage since you're executing two prompts that may make many API calls but used more effectively than a human would since they parse context so fast.

**When is it worse?**

It's worse when you need ownership, you're working on a team, and have to take accountability for the code you're outputting. I feel very disconnected from the end product. If I was doing a code review with a team, I would only be able to answer a few implementation/design decisions that went into the app because the agent did it all for me. I feel like I have no ownership over this codebase unless I spent more time reading it and playing around with it. I don't feel super proud of it because I didn't capture enough understanding of it. Sometimes, letting an agent do all the work makes me feel like a fraud/imposter. On top of that, since it's so nice and polished I don't have any real motivation to understand the codebase either because the end product is great and it works well enough.
