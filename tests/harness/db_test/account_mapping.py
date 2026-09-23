"""DB 배치 입력의 실제 계정을 MMR 귀속 본캐에 연결한다."""

from __future__ import annotations

import pandas as pd


def attach_mmr_player_account(matches: pd.DataFrame, members: pd.DataFrame) -> pd.DataFrame:
    """guild_member 관계를 검증하고 원본 player_code를 보존한다."""
    required = {"guild_id", "account", "main_account", "is_main"}
    missing = required - set(members.columns)
    if missing:
        raise ValueError(f"guild_member mapping is missing columns: {sorted(missing)}")

    if matches[["guild_id", "player_code"]].isna().any().any():
        raise ValueError("MMR matches require guild_id and player_code before account mapping.")

    members = members.copy()
    members["account"] = members["account"].astype("string").str.strip()
    members["main_account"] = members["main_account"].astype("string").str.strip()
    if members[["guild_id", "account"]].isna().any().any() or members["account"].eq("").any():
        raise ValueError("guild_member contains an empty account or guild_id.")
    if members.duplicated(["guild_id", "account"]).any():
        raise ValueError("guild_member contains duplicate guild/account relationships.")
    if members["is_main"].isna().any():
        raise ValueError("guild_member contains NULL is_main.")

    alt = members["is_main"].eq(False)
    invalid_main = alt & (members["main_account"].isna() | members["main_account"].eq(""))
    if invalid_main.any():
        sample = members.loc[invalid_main, ["guild_id", "account"]].head().to_dict("records")
        raise ValueError(f"MISSING_MAIN_ACCOUNT: {sample}")

    targets = members.loc[members["is_main"].eq(True), ["guild_id", "account"]].rename(
        columns={"account": "main_account"}
    )
    alt_members = members.loc[alt, ["guild_id", "account", "main_account"]]
    target_check = alt_members.merge(
        targets, on=["guild_id", "main_account"], how="left", indicator=True, validate="many_to_one"
    )
    if target_check["_merge"].ne("both").any():
        sample = target_check.loc[target_check["_merge"].ne("both"), ["guild_id", "account", "main_account"]].head().to_dict("records")
        raise ValueError(f"INVALID_MAIN_ACCOUNT: {sample}")

    members["mmr_player_account"] = members["account"].where(~alt, members["main_account"])
    mapping = members[["guild_id", "account", "mmr_player_account"]]
    out = matches.merge(
        mapping, left_on=["guild_id", "player_code"], right_on=["guild_id", "account"],
        how="left", validate="many_to_one", sort=False,
    ).drop(columns=["account"])
    # Historical games can contain accounts with no current guild_member row.
    out["mmr_player_account"] = out["mmr_player_account"].fillna(out["player_code"])
    return out


def reject_duplicate_mmr_accounts(matches: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """동일 경기에서 한 본캐에 두 참가자가 귀속되면 경기 전체를 제외한다."""
    keys = ["guild_id", "replay_code", "mmr_player_account"]
    duplicate = matches.duplicated(keys, keep=False)
    if not duplicate.any():
        return matches.copy(), []

    conflicts = matches.loc[duplicate, [*keys, "player_code"]]
    rejected = []
    for (guild_id, replay_code), group in conflicts.groupby(["guild_id", "replay_code"], sort=False):
        rejected.append({
            "guild_id": guild_id,
            "replay_code": replay_code,
            "reason_code": "DUPLICATE_MMR_ACCOUNT",
            "mmr_player_accounts": group["mmr_player_account"].drop_duplicates().tolist(),
            "player_codes": group["player_code"].drop_duplicates().tolist(),
        })
    rejected_keys = pd.DataFrame(rejected)[["guild_id", "replay_code"]]
    filtered = matches.merge(rejected_keys.assign(_rejected=True), on=["guild_id", "replay_code"], how="left")
    filtered = filtered.loc[filtered["_rejected"].isna(), matches.columns]
    return filtered.reset_index(drop=True), rejected
