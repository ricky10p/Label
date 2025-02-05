import time

class SessionManager:
    def __init__(self):
        self.sessions = {}

    def save_results(self, user_id, results):
        self.sessions[user_id] = {
            'results': results,
            'timestamp': time.time()
        }

    def get_results(self, user_id):
        session = self.sessions.get(user_id)
        if session and (time.time() - session['timestamp']) < 300:  # Sesi berlaku selama 5 menit
            return session['results']
        return None

    def save_selected_address(self, user_id, address):
        if user_id in self.sessions:
            self.sessions[user_id]['selected_address'] = address

    def get_selected_address(self, user_id):
        session = self.sessions.get(user_id)
        if session and (time.time() - session['timestamp']) < 300:  # Sesi berlaku selama 5 menit
            return session.get('selected_address')
        return None
