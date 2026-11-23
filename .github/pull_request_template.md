## My listing

What it is, in a sentence or two:

## Checklist

The format is [`contracts/listing.v1.md`](https://github.com/openwizdev/WizMarket/blob/main/contracts/listing.v1.md); the [README](https://github.com/openwizdev/WizMarket/blob/main/README.md#publish-your-own) walks through it.

- [ ] This pull request adds or changes one listing, in one file, `listings/<id>.json` (plus its receipt, for a verified driver or harness), where `<id>` is 2 to 40 lowercase letters, digits or hyphens, and is not written inside the file.
- [ ] It has only the contract's fields, and `url` and every link are `https://` URLs as the contract allows.
- [ ] Its `tags` are my own choice: 1 to 8, lowercase letters, digits and hyphens, none twice.
- [ ] If its `stage` is `being-built`, the first entry of `links` is the public pull request or ticket where it is being built.
- [ ] Its `status` is `listed`, with no `proof`, unless I add my kind's proof (tagged both, I add both):
  - [ ] `driver` or `harness`: the kit receipt from the real host, added at `receipts/<id>/<date>-<commit>.txt` in the contract's receipt format, and named in `proof.receipt`.
  - [ ] `skill`: `proof.source` pins a public GitHub repository at a full 40-character commit, and `proof.check` is the command that passes there (exit 0).
- [ ] Nothing private: no token, key or password, no private id (a thread, session or machine id), no path on your own machine (such as one in your home folder), in the listing or the receipt.
- [ ] I ran `python3 -I check/check.py check` from the repository's root and it printed `check: ok`.
