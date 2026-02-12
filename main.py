import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
import random

# Récupération du token depuis les variables d'environnement Railway
TOKEN = os.getenv('TOKEN')
if not TOKEN:
    raise ValueError("Le token n'est pas défini dans les variables d'environnement")

class GiveawayBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        intents.members = True
        
        super().__init__(
            command_prefix="!",  # Préfixe optionnel pour les commandes classiques
            intents=intents,
            application_id=os.getenv('APPLICATION_ID')  # Optionnel
        )
        
        self.active_giveaways = {}
        self.authorized_users = set()
        self.initial_extensions = []

    async def setup_hook(self):
        """Hook d'initialisation appelé au démarrage"""
        await self.add_cog(GiveawayCog(self))
        await self.tree.sync()  # Synchronisation des commandes slash
        print(f"Commandes slash synchronisées pour {self.user}")

    async def on_ready(self):
        """Événement déclenché quand le bot est prêt"""
        print(f"{self.user} est connecté et prêt sur Railway !")
        print(f"Latence : {round(self.latency * 1000)}ms")
        
        # Status personnalisé
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="les giveaways | /giveaway"
            )
        )

class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.check_expired_giveaways())

    async def check_expired_giveaways(self):
        """Vérifie les giveaways expirés toutes les minutes"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                current_time = datetime.utcnow()
                expired = []
                
                for message_id, data in self.bot.active_giveaways.items():
                    if current_time >= data["end_time"]:
                        expired.append(message_id)
                
                for message_id in expired:
                    await self.end_giveaway(message_id)
                
                await asyncio.sleep(60)  # Vérification toutes les minutes
            except Exception as e:
                print(f"Erreur check_expired_giveaways: {e}")
                await asyncio.sleep(60)

    @app_commands.command(name="giveaway", description="Lance un giveaway")
    async def giveaway(
        self, 
        interaction: discord.Interaction, 
        gain: str,
        temps: str,
        salon: discord.TextChannel,
        nombre_de_gagnants: app_commands.Range[int, 1, 25] = 1,
        emoji: str = "🎉"
    ):
        """Commande slash pour créer un giveaway"""
        
        # Vérification des permissions
        if (interaction.user.id not in self.bot.authorized_users and 
            not interaction.user.guild_permissions.administrator):
            embed_error = discord.Embed(
                description="❌ Vous n'êtes pas autorisé à utiliser cette commande.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Parser le temps
            time_unit = temps[-1].lower()
            time_value = int(temps[:-1])
            
            if time_unit == 's':
                duration = timedelta(seconds=time_value)
            elif time_unit == 'm':
                duration = timedelta(minutes=time_value)
            elif time_unit == 'h':
                duration = timedelta(hours=time_value)
            elif time_unit == 'j':
                duration = timedelta(days=time_value)
            else:
                embed_error = discord.Embed(
                    description="❌ Format de temps invalide. Utilisez `s`, `m`, `h` ou `j`",
                    color=0xFF0000
                )
                await interaction.followup.send(embed=embed_error, ephemeral=True)
                return

            end_time = datetime.utcnow() + duration

            # Création de l'embed blanc
            embed = discord.Embed(
                title="**Giveaway**",
                description=f"```\nGain : {gain}\n\nDurée : {temps}\n\nNombre de gagnants : {nombre_de_gagnants}\n\n```",
                color=0xFFFFFF
            )
            
            embed.add_field(name="\u200b", value="─" * 50, inline=False)
            embed.set_footer(text=f"ID: {interaction.id}")

            # Création du bouton
            view = GiveawayView(emoji, end_time, nombre_de_gagnants, gain, salon.id)
            
            # Envoi du message
            giveaway_message = await salon.send(embed=embed, view=view)
            view.message = giveaway_message  # Lier la vue au message
            
            # Stocker les infos du giveaway
            self.bot.active_giveaways[giveaway_message.id] = {
                "end_time": end_time,
                "winners": nombre_de_gagnants,
                "prize": gain,
                "emoji": emoji,
                "channel_id": salon.id,
                "message_id": giveaway_message.id,
                "host_id": interaction.user.id
            }

            # Confirmation
            embed_confirm = discord.Embed(
                description=f"✅ Giveaway créé avec succès dans {salon.mention} !",
                color=0x00FF00
            )
            await interaction.followup.send(embed=embed_confirm, ephemeral=True)

        except ValueError:
            embed_error = discord.Embed(
                description="❌ Erreur: Format de temps invalide. Exemple: `10s`, `5m`, `2h`, `1j`",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)
        except Exception as e:
            embed_error = discord.Embed(
                description=f"❌ Une erreur est survenue: {str(e)}",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)

    @app_commands.command(name="reroll", description="Choisit de nouveaux gagnants pour un giveaway")
    async def reroll(self, interaction: discord.Interaction, id_du_message: str):
        """Commande slash pour refaire un tirage"""
        
        # Vérification des permissions
        if (interaction.user.id not in self.bot.authorized_users and 
            not interaction.user.guild_permissions.administrator):
            embed_error = discord.Embed(
                description="❌ Vous n'êtes pas autorisé à utiliser cette commande.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            message_id = int(id_du_message)
        except ValueError:
            embed_error = discord.Embed(
                description="❌ ID de message invalide.",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)
            return

        # Chercher le message dans tous les salons
        message = None
        for channel in interaction.guild.channels:
            if isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(message_id)
                    break
                except:
                    continue

        if not message:
            embed_error = discord.Embed(
                description="❌ Message non trouvé. Vérifiez l'ID.",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)
            return

        await self.select_winners(message, interaction)

    @app_commands.command(name="autorise", description="Autorise un utilisateur aux commandes giveaway")
    async def autorise(self, interaction: discord.Interaction, user: discord.User):
        """Commande slash pour autoriser un utilisateur"""
        
        # Seuls les admins peuvent utiliser cette commande
        if not interaction.user.guild_permissions.administrator:
            embed_error = discord.Embed(
                description="❌ Seuls les administrateurs peuvent utiliser cette commande.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return

        self.bot.authorized_users.add(user.id)
        
        embed_success = discord.Embed(
            description=f"✅ {user.mention} est maintenant autorisé à utiliser les commandes giveaway.",
            color=0x00FF00
        )
        await interaction.response.send_message(embed=embed_success, ephemeral=True)

    @app_commands.command(name="stop", description="Arrête un giveaway en cours")
    async def stop_giveaway(self, interaction: discord.Interaction, id_du_message: str):
        """Commande slash pour arrêter un giveaway"""
        
        if (interaction.user.id not in self.bot.authorized_users and 
            not interaction.user.guild_permissions.administrator):
            embed_error = discord.Embed(
                description="❌ Vous n'êtes pas autorisé à utiliser cette commande.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return

        try:
            message_id = int(id_du_message)
        except ValueError:
            embed_error = discord.Embed(
                description="❌ ID de message invalide.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return

        if message_id in self.bot.active_giveaways:
            del self.bot.active_giveaways[message_id]
            embed_success = discord.Embed(
                description="✅ Giveaway arrêté avec succès.",
                color=0x00FF00
            )
            await interaction.response.send_message(embed=embed_success, ephemeral=True)
        else:
            embed_error = discord.Embed(
                description="❌ Giveaway non trouvé ou déjà terminé.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)

    async def end_giveaway(self, message_id: int):
        """Termine un giveaway et sélectionne les gagnants"""
        try:
            if message_id not in self.bot.active_giveaways:
                return

            data = self.bot.active_giveaways[message_id]
            channel = self.bot.get_channel(data["channel_id"])
            
            if not channel:
                return
                
            try:
                message = await channel.fetch_message(message_id)
            except:
                del self.bot.active_giveaways[message_id]
                return

            await self.select_winners(message)
            
        except Exception as e:
            print(f"Erreur end_giveaway: {e}")

    async def select_winners(self, message: discord.Message, interaction: discord.Interaction = None):
        """Sélectionne les gagnants d'un giveaway"""
        
        message_id = message.id
        
        if message_id not in self.bot.active_giveaways:
            return

        data = self.bot.active_giveaways[message_id]
        winners_count = data["winners"]
        prize = data["prize"]
        emoji = data["emoji"]

        # Récupérer les participants
        participants = []
        
        # Vérifier les réactions
        for reaction in message.reactions:
            if str(reaction.emoji) == emoji:
                async for user in reaction.users():
                    if not user.bot:
                        participants.append(user)
                break

        # Sélectionner les gagnants
        if len(participants) < winners_count:
            winner_text = "Pas assez de participants"
        else:
            winners = random.sample(participants, min(winners_count, len(participants)))
            winner_text = " ".join([winner.mention for winner in winners])

        # Message de fin
        end_embed = discord.Embed(
            title="🎉 Giveaway Terminé 🎉",
            description=f"**Gain:** {prize}",
            color=0xFFFFFF
        )
        
        if winners_count == 1:
            end_embed.add_field(name="**Gagnant**", value=winner_text, inline=False)
        else:
            end_embed.add_field(name="**Gagnants**", value=winner_text, inline=False)

        end_embed.set_footer(text=f"Total participants: {len(participants)}")

        await message.reply(embed=end_embed)
        
        # Désactiver le bouton
        try:
            view = discord.ui.View(timeout=None)
            disabled_button = discord.ui.Button(
                style=discord.ButtonStyle.gray,
                label="participer",
                emoji=emoji,
                disabled=True
            )
            view.add_item(disabled_button)
            await message.edit(view=view)
        except:
            pass

        # Supprimer des giveaways actifs
        del self.bot.active_giveaways[message_id]

class GiveawayView(discord.ui.View):
    """View pour le bouton de participation"""
    
    def __init__(self, emoji: str, end_time: datetime, winners: int, prize: str, channel_id: int):
        super().__init__(timeout=None)
        self.emoji = emoji
        self.end_time = end_time
        self.winners = winners
        self.prize = prize
        self.channel_id = channel_id
        self.participants = set()
        self.message = None

    @discord.ui.button(label="participer", style=discord.ButtonStyle.gray)
    async def participate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton de participation"""
        
        # Ajouter l'emoji au bouton
        button.emoji = self.emoji
        
        if interaction.user.bot:
            await interaction.response.send_message("Les bots ne peuvent pas participer !", ephemeral=True)
            return

        user_id = interaction.user.id
        
        if user_id in self.participants:
            await interaction.response.send_message("❌ Vous participez déjà à ce giveaway !", ephemeral=True)
        else:
            self.participants.add(user_id)
            await interaction.response.send_message("✅ Participation enregistrée ! Bonne chance !", ephemeral=True)

        # Mettre à jour le compteur dans le footer
        if self.message:
            embed = self.message.embeds[0]
            embed.set_footer(text=f"Participants: {len(self.participants)} • Fin: {self.end_time.strftime('%d/%m/%Y %H:%M:%S')}")
            await self.message.edit(embed=embed)

# Initialisation du bot
bot = GiveawayBot()

@bot.event
async def on_error(event, *args, **kwargs):
    """Gestion globale des erreurs"""
    print(f"Erreur dans l'événement {event}: {args[0] if args else 'Unknown'}")

if __name__ == "__main__":
    if TOKEN:
        try:
            bot.run(TOKEN)
        except discord.LoginFailure:
            print("Erreur: Token invalide. Vérifiez la variable d'environnement TOKEN sur Railway.")
        except Exception as e:
            print(f"Erreur de démarrage: {e}")
    else:
        print("Erreur: Token non trouvé. Définissez TOKEN dans les variables d'environnement Railway.")