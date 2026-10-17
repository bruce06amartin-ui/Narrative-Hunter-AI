"""
Shared liquidity-manipulation sanity check.

Real pools should see meaningful trading volume relative to their claimed
liquidity size. A coin claiming huge liquidity with near-zero volume is a
known DeFi manipulation pattern (fake reserves reported to indexers to
appear significant to bots/scanners) - confirmed via real production
data: a coin showing $180M+ liquidity had only ~$2,000 in 24h volume, an
~86,000:1 ratio that's essentially impossible for genuine trading
activity.

Originally built only into the Solana wallet-check prioritization query,
then found to be needed more broadly: the same manipulated coins were
still getting a perfect liquidity_score (and therefore a real boost to
overall_score) since the core scoring math never applied this check at
all - only the one narrow query did. Moved here as a single shared
source of truth so both places stay in sync rather than risking drift
between two separately-maintained copies of the same logic.
"""

# Only apply this check to coins claiming large enough liquidity that a
# total absence of real trading is actually implausible - small coins
# naturally have noisy, low volume regardless of legitimacy.
MANIPULATION_CHECK_MIN_LIQUIDITY_USD = 1_000_000.0
# A genuinely active pool should see at least this fraction of its claimed
# liquidity in daily volume - 0.05% is a deliberately low bar (most real
# pools clear it easily), chosen to only catch the extreme manipulation
# pattern actually observed, not to penalize merely-quiet-but-real coins.
MIN_VOLUME_TO_LIQUIDITY_RATIO = 0.0005


def is_liquidity_plausible(liquidity_usd: float | None, volume_24h_usd: float | None) -> bool:
    """True if this coin's claimed liquidity is trustworthy enough to use
    in scoring/prioritization. False signals likely manipulated/fake
    reserve data (huge claimed liquidity, implausibly little real
    trading behind it)."""
    if not liquidity_usd or liquidity_usd < MANIPULATION_CHECK_MIN_LIQUIDITY_USD:
        return True
    if volume_24h_usd is None:
        return True
    return volume_24h_usd >= liquidity_usd * MIN_VOLUME_TO_LIQUIDITY_RATIO


# A coin with essentially zero real trading activity right now, regardless
# of whether its liquidity figure is genuine or manipulated. Distinct from
# the manipulation check above: that one targets FAKE liquidity claims;
# this one targets coins that have simply stopped being traded at all -
# a real pattern reported directly by a user: pump.fun coins whose bot
# alerts kept pointing to charts where the last real transaction was
# 3-11+ hours old, well after any real activity had ended.
MIN_ABSOLUTE_VOLUME_USD = 50.0


def is_actively_trading(volume_24h_usd: float | None) -> bool:
    """True if a coin shows at least some real, current trading activity.
    False if 24h volume is at or near zero - the clearest proxy available
    for "this coin has effectively stopped trading", given this project
    doesn't track individual transaction timestamps. Note: volume_24h_usd
    is a ROLLING 24-hour total, not a "time since last trade" figure - a
    coin whose last real trade was 11 hours ago could still show some
    nonzero volume from earlier in that same window, so this is a real
    but imperfect proxy, not a precise "still trading this exact minute"
    guarantee."""
    if volume_24h_usd is None:
        return True  # unknown - don't penalize for missing data
    return volume_24h_usd >= MIN_ABSOLUTE_VOLUME_USD
