class UserRepository:

    def __init__(self, session: Session) -> None:
        self.session = session

    # Implements CanRead[User, UserId]
    def get_by_id(self, id: UserId) -> Optional[User]:
        return self.session.get(User, id)

    # Implements CanCreate[User, UserCreate]
    def create(self, data: UserCreate) -> User:
        # User.model_validate converts the UserCreate payload into a User table entity
        db_user = User.model_validate(data)

        self.session.add(db_user)
        self.session.commit()
        self.session.refresh(db_user)
        return db_user

    # Implements CanUpdate[User]
    def update(self, entity: User) -> User:
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    # Implements CanDelete[UserId]
    def delete(self, id: UserId) -> None:
        user = self.get_by_id(id)
        if user:
            self.session.delete(user)
            self.session.commit()
