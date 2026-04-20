import sqlite3

def display_users():
    # Connect to the SQLite database
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # Query to fetch all users except the password hash for safety
    cursor.execute("SELECT id, name, location, mobile, email, created_at FROM users")
    rows = cursor.fetchall()
    
    # Print the data in a neat table format
    print(f"\n{'-'*95}")
    print(f"{'ID':<5} | {'Name':<15} | {'Location':<15} | {'Mobile':<12} | {'Email':<25} | {'Registered At'}")
    print(f"{'-'*95}")
    
    if not rows:
        print("No users found in the database.")
    
    for row in rows:
        print(f"{row[0]:<5} | {row[1]:<15} | {row[2]:<15} | {row[3]:<12} | {row[4]:<25} | {row[5]}")
        
    print(f"{'-'*95}\n")
    conn.close()

if __name__ == '__main__':
    display_users()
