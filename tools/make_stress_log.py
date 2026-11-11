#!/usr/bin/env python3
"""Write a Game.log with deliberately awkward content for layout checks.

Very long place / contract / ship / crew names, many objectives, every status pill at once,
several injuries, big money amounts. Used by ``tools/ui_audit.js``.

    python tools/make_stress_log.py stress.log
"""

import sys

LINES = [
    '<2026-11-11T15:00:00.000Z> Log started',
    '<2026-11-11T15:00:01.000Z> ProductVersion: 4.10.197.2878',
    '<2026-11-11T15:00:02.000Z> [Notice] <Legacy login response> [CIG-net] User Login Success - Handle[A_Very_Long_Pilot_Handle_Name] - Time[1] [Team_GameServices][Login]',
    '<2026-11-11T15:00:03.000Z> [Notice] <Join PU> address[10.0.0.1] port[1] shard[pub_euw1b_12881860_100] locationId[1] [Team_GameServices][GIM]',
    '<2026-11-11T15:00:04.000Z> [Notice] <RequestLocationInventory> Player[A_Very_Long_Pilot_Handle_Name] requested inventory for Location[Stanton4_DistributionCentre_Covalex_S4DC05] [Team_CoreGameplayFeatures][Inventory]',
    '<2026-11-11T15:00:05.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "You have joined channel \'Anvil Carrack Expedition w/ C8X Pisces : A_Very_Long_Pilot_Handle_Name\'.: " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:06.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "New Member Joined Bob_the_Very_Long_Named_Hauler has joined channel \'Anvil Carrack Expedition w/ C8X Pisces : A_Very_Long_Pilot_Handle_Name\': " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:07.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "New Member Joined Alice_Second_Crew_Member has joined channel \'Anvil Carrack Expedition w/ C8X Pisces : A_Very_Long_Pilot_Handle_Name\': " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:08.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "New Member Joined Charlie_Third has joined channel \'Anvil Carrack Expedition w/ C8X Pisces : A_Very_Long_Pilot_Handle_Name\': " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:09.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Leaving Armistice Zone - Caution Advised: " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:10.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Exited Monitored Space: " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:11.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Journal Entry Added: Jurisdiction: Ungoverned: " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:12.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Restricted Area - Vehicles will be impounded: " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:13.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Entering Private Property: " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:14.000Z> [Notice] <Player Selected Quantum Target - Local> [ItemNavigation][CL][1] | NOT AUTH | ANVL_Carrack_123456789[123456789]|CSCItemNavigation::OnPlayerSelectedQuantumTarget|Player has selected point Stanton1_Teasa_Spaceport_Lorville_Terminal_Long_Name as their destination, routing locally [Team_CGP4][QuantumTravel]',
    '<2026-11-11T15:00:15.000Z> [Notice] <Calculate Route> [ItemNavigation][CL][1] | NOT AUTH | ANVL_Carrack_123456789[123456789]|CSCItemNavigation::CalculateRoute|Successfully calculated route to Stanton1_Teasa_Spaceport_Lorville_Terminal_Long_Name fuel estimate 1234567.0 [Team_CGP4][QuantumTravel]',
    '<2026-11-11T15:00:16.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted: Priority Hauling - Hurston Dynamics Bulk Transfer to microTech Logistics Network (Rush): " [1] to queue. New queue size: 1, MissionId: [m1], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:17.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Pick up 960 SCU of Processed Food from Lorville Central Business District Cargo Center on Hurston: " [1] to queue. New queue size: 1, MissionId: [m1], ObjectiveId: [pickup_1] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:18.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Deliver 312/960 SCU of Processed Food to Port Tressler above microTech in orbit: " [1] to queue. New queue size: 1, MissionId: [m1], ObjectiveId: [dropoff_1] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:19.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Deliver 0/120 SCU of Medical Supplies to Clear View Emergency Shelter on microTech: " [1] to queue. New queue size: 1, MissionId: [m1], ObjectiveId: [dropoff_2] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:20.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Return to the contractor at Everus Harbor and report the successful transfer: " [1] to queue. New queue size: 1, MissionId: [m1], ObjectiveId: [o4] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:21.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Avoid detection by UEE Advocacy patrols near the jump point: " [1] to queue. New queue size: 1, MissionId: [m1], ObjectiveId: [o5] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:22.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Optional bonus - keep cargo integrity above 90 percent: " [1] to queue. New queue size: 1, MissionId: [m1], ObjectiveId: [o6] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:23.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Optional bonus 2 - finish within 45 minutes: " [1] to queue. New queue size: 1, MissionId: [m1], ObjectiveId: [o7] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:24.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted: Bounty Hunting - Very High Risk Target - Outlaw Leader Near Yela: " [1] to queue. New queue size: 1, MissionId: [m2], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:25.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted: Salvage Contract: Recover Black Box from Derelict Hull: " [1] to queue. New queue size: 1, MissionId: [m3], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:26.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted: Mercenary Defend Location: Outpost Defense on Daymar: " [1] to queue. New queue size: 1, MissionId: [m4], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:27.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Minor Injury Detected - Left Arm - Tier 3 Treatment Required: " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:28.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Moderate Injury Detected - Right Leg - Tier 2 Treatment Required: " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:29.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Severe Injury Detected - Head - Tier 1 Treatment Required: " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:30.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "CrimeStat Rating Increased: " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:31.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Bob_the_Very_Long_Named_Hauler has sent you: 1,250,000 aUEC: " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:32.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Fined 15000 UEC: " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T15:00:33.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Air Traffic Control (ATC): To receive a hangar assignment or permission to take-off, contact landing services via the Comms menu on your MFD or in your mobiGlas.: " [1] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    '<2026-11-11T16:00:06.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted: Banner Test With A Really Quite Long Contract Name For Layout 1280: " [9] to queue. MissionId: [b1280], ObjectiveId: []',
]


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "stress.log"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\r\n".join(LINES) + "\r\n")
    print(f"{len(LINES)} lines -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
