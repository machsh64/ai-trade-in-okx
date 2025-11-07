from sqlalchemy.orm import Session
from typing import Optional, List
from database.models import Account, User
from decimal import Decimal


def create_account(
    db: Session,
    user_id: int,
    name: str,
    account_type: str = "AI",
    initial_capital: float = 10000.0,
    model: str = "gpt-4-turbo",
    base_url: str = "https://api.openai.com/v1",
    api_key: str = None,
    okx_api_key: str = None,
    okx_secret: str = None,
    okx_passphrase: str = None,
    okx_sandbox: str = "true"
) -> Account:
    """Create a new trading account"""
    account = Account(
        user_id=user_id,
        version="v1",
        name=name,
        account_type=account_type,
        model=model if account_type == "AI" else None,
        base_url=base_url if account_type == "AI" else None,
        api_key=api_key if account_type == "AI" else None,
        okx_api_key=okx_api_key,
        okx_secret=okx_secret,
        okx_passphrase=okx_passphrase,
        okx_sandbox=okx_sandbox or "true",
        initial_capital=initial_capital,
        current_cash=initial_capital,
        frozen_cash=0.0,
        is_active="true"
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def get_account(db: Session, account_id: int) -> Optional[Account]:
    """Get account by ID"""
    return db.query(Account).filter(Account.id == account_id).first()


def get_accounts_by_user(db: Session, user_id: int, active_only: bool = True) -> List[Account]:
    """Get all accounts for a user"""
    query = db.query(Account).filter(Account.user_id == user_id)
    if active_only:
        query = query.filter(Account.is_active == "true")
    return query.all()


def get_or_create_default_account(
    db: Session,
    user_id: int,
    account_name: str = "Default AI Trader",
    initial_capital: float = 10000.0,
    model: str = "gpt-4-turbo",
    base_url: str = "https://api.openai.com/v1",
    api_key: str = "default-key-please-update-in-settings"
) -> Account:
    """Get existing account or create default AI account for user"""
    # Check if user has any accounts
    existing_accounts = get_accounts_by_user(db, user_id, active_only=True)
    if existing_accounts:
        return existing_accounts[0]  # Return first active account
    
    # Create default AI account
    return create_account(
        db=db,
        user_id=user_id,
        name=account_name,
        account_type="AI",
        initial_capital=initial_capital,
        model=model,
        base_url=base_url,
        api_key=api_key
    )


def update_account(
    db: Session,
    account_id: int,
    name: str = None,
    model: str = None,
    base_url: str = None,
    api_key: str = None,
    okx_api_key: str = None,
    okx_secret: str = None,
    okx_passphrase: str = None,
    okx_sandbox: str = None
) -> Optional[Account]:
    """Update account information
    
    Note: For OKX fields, masked values (starting with ****) will not update the database.
    This prevents accidentally overwriting real credentials with masked display values.
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return None
    
    if name is not None:
        account.name = name
    if model is not None:
        account.model = model
    if base_url is not None:
        account.base_url = base_url
    if api_key is not None:
        account.api_key = api_key
    
    # Only update OKX fields if they are not masked values
    if okx_api_key is not None:
        if okx_api_key and not okx_api_key.startswith("****"):
            account.okx_api_key = okx_api_key
        elif not okx_api_key:
            # Allow explicit clearing with empty string
            account.okx_api_key = None
    
    if okx_secret is not None:
        if okx_secret and not okx_secret.startswith("****"):
            account.okx_secret = okx_secret
        elif not okx_secret:
            account.okx_secret = None
    
    if okx_passphrase is not None:
        if okx_passphrase and not okx_passphrase.startswith("****"):
            account.okx_passphrase = okx_passphrase
        elif not okx_passphrase:
            account.okx_passphrase = None
    
    if okx_sandbox is not None:
        account.okx_sandbox = okx_sandbox
    
    db.commit()
    db.refresh(account)
    return account


def update_account_cash(
    db: Session,
    account_id: int,
    current_cash: float,
    frozen_cash: float = None
) -> Optional[Account]:
    """Update account cash balance"""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return None
    
    account.current_cash = current_cash
    if frozen_cash is not None:
        account.frozen_cash = frozen_cash
    
    db.commit()
    db.refresh(account)
    return account


def deactivate_account(db: Session, account_id: int) -> Optional[Account]:
    """Deactivate an account"""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return None
    
    account.is_active = "false"
    db.commit()
    db.refresh(account)
    return account


def activate_account(db: Session, account_id: int) -> Optional[Account]:
    """Activate an account"""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return None
    
    account.is_active = "true"
    db.commit()
    db.refresh(account)
    return account