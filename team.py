import random
import time

def main():
    print("=========================================")
    print(" 🚀 TEAM TASK SIMULATOR: THE GRIND 🚀")
    print("=========================================\n")

    # 1. Get the main character
    main_character = input("Who is the Main Character (Team Leader)? ")

    # 2. Ask for the number of individuals in the team
    while True:
        try:
            num_members = int(input(f"How many other individuals are in {main_character}'s team? "))
            if num_members > 0:
                break
            else:
                print("Please enter a number greater than 0.")
        except ValueError:
            print("Invalid input. Please enter a valid number.")

    # 3. Add people to the team list
    team_members = []
    print("\n--- Add Team Members ---")
    for i in range(num_members):
        member_name = input(f"Enter the name of team member {i + 1}: ")
        team_members.append(member_name)

    # 4. Add 10 tasks
    print("\n--- Add 10 Tasks ---")
    print(f"Let's figure out what the team needs to do today.")
    tasks = []
    for i in range(10):
        task = input(f"Task {i + 1}: ")
        tasks.append(task)

    # 5. Ask for the duration of the simulation
    while True:
        try:
            duration = int(input("\nHow many minutes should we simulate this work session? "))
            if duration > 0:
                break
            else:
                print("Please enter a time greater than 0.")
        except ValueError:
            print("Invalid input. Please enter a valid number of minutes.")

    # 6. Assign tasks ONLY to the team members (Main character delegates and helps)
    assignments = {person: [] for person in team_members}
    
    # Distribute tasks randomly to the team
    for task in tasks:
        random_assignee = random.choice(team_members)
        assignments[random_assignee].append(task)

    # Display initial assignments
    print("\n=========================================")
    print("          📋 INITIAL ASSIGNMENTS 📋      ")
    print("=========================================")
    print(f"👑 {main_character} is the Leader and will float between tasks!")
    for person, assigned_tasks in assignments.items():
        print(f"\n👤 {person}:")
        if not assigned_tasks:
            print("   ↳ 🍀 Lucky! No specific tasks assigned. They are on standby.")
        else:
            for t in assigned_tasks:
                print(f"   ↳ [ ] {t}")
                
    print("\nPress ENTER to start the simulation...")
    input()

    # 7. THE TIME LOOP
    print("=========================================")
    print("             ⏱️ SIMULATION START ⏱️           ")
    print("=========================================\n")

    for minute in range(1, duration + 1):
        print(f"--- 🕒 Minute {minute} ---")
        
        # Pick a random team member for the Main Character to help this minute
        helped_member = random.choice(team_members)
        
        # Determine what the helped member is working on
        if assignments[helped_member]:
            # They work on one of their assigned tasks
            current_joint_task = random.choice(assignments[helped_member])
        else:
            # If they had no assigned tasks, they pick a random one from the master list to help with
            current_joint_task = random.choice(tasks)
            
        print(f"🌟 👑 {main_character} is currently teaming up with {helped_member} to work on: '{current_joint_task}'!")
        
        # Show what the REST of the team is doing
        for member in team_members:
            if member != helped_member:
                if assignments[member]:
                    # Pick a random task from their own list to be actively doing
                    active_task = random.choice(assignments[member])
                    print(f"   👤 {member} is independently tackling: '{active_task}'")
                else:
                    print(f"   👤 {member} is currently organizing files and waiting for instructions.")
        
        print("") # Blank line for readability
        time.sleep(1.5) # Pauses the code for 1.5 seconds so it feels like a real-time feed

    print("=========================================")
    print("            🏁 SIMULATION COMPLETE 🏁         ")
    print("=========================================")
    print(f"Great job, {main_character} and team!")

if __name__ == "__main__":
    main()